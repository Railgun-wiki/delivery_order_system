import json
import sqlite3
from dataclasses import dataclass


@dataclass
class Order:
    order_id: int
    user: str
    restaurant: str
    items: list

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "user": self.user,
            "restaurant": self.restaurant,
            "items": self.items,
        }


class DeliveryOrderSystem:
    def __init__(self, db_path=":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user TEXT,
                    restaurant TEXT,
                    items TEXT,
                    status TEXT,
                    note TEXT,
                    completion_seq INTEGER
                );
                CREATE TABLE IF NOT EXISTS undo_stack (
                    undo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER
                );
            ''')

    def place_order(self, user, restaurant, items):
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO orders (user, restaurant, items, status) VALUES (?, ?, ?, 'WAITING')",
                (user, restaurant, json.dumps(list(items)))
            )
            order_id = cursor.lastrowid
        return f"Order placed: #{order_id} for {user}"

    @property
    def current_order(self):
        cur = self.conn.execute("SELECT * FROM orders WHERE status = 'CURRENT'").fetchone()
        if not cur:
            return None
        return Order(
            order_id=cur["order_id"],
            user=cur["user"],
            restaurant=cur["restaurant"],
            items=json.loads(cur["items"])
        )

    def dispatch_next_order(self):
        with self.conn:
            cur = self.conn.execute("SELECT order_id FROM orders WHERE status = 'CURRENT'").fetchone()
            if cur:
                return f"Cannot dispatch: current order #{cur['order_id']} is not completed yet"

            waiting = self.conn.execute("SELECT order_id FROM orders WHERE status = 'WAITING' ORDER BY order_id ASC LIMIT 1").fetchone()
            if not waiting:
                return "No waiting orders to dispatch"

            order_id = waiting['order_id']
            self.conn.execute("UPDATE orders SET status = 'CURRENT' WHERE order_id = ?", (order_id,))
        return f"Dispatched order #{order_id}"

    def complete_current_order(self, note):
        with self.conn:
            cur = self.conn.execute("SELECT order_id FROM orders WHERE status = 'CURRENT'").fetchone()
            if not cur:
                return "No current order to complete"

            order_id = cur['order_id']
            seq_row = self.conn.execute("SELECT MAX(completion_seq) as max_seq FROM orders").fetchone()
            next_seq = (seq_row['max_seq'] or 0) + 1

            self.conn.execute(
                "UPDATE orders SET status = 'COMPLETED', note = ?, completion_seq = ? WHERE order_id = ?",
                (note, next_seq, order_id)
            )
            self.conn.execute("INSERT INTO undo_stack (order_id) VALUES (?)", (order_id,))
        return f"Completed order #{order_id}"

    def undo_last_completion(self):
        with self.conn:
            cur = self.conn.execute("SELECT order_id FROM orders WHERE status = 'CURRENT'").fetchone()
            if cur:
                return f"Cannot undo now: current order #{cur['order_id']} is in progress"

            last_undo = self.conn.execute("SELECT undo_id, order_id FROM undo_stack ORDER BY undo_id DESC LIMIT 1").fetchone()
            if not last_undo:
                return "No completion record to undo"

            undo_id, order_id = last_undo['undo_id'], last_undo['order_id']
            self.conn.execute("UPDATE orders SET status = 'CURRENT', note = NULL, completion_seq = NULL WHERE order_id = ?", (order_id,))
            self.conn.execute("DELETE FROM undo_stack WHERE undo_id = ?", (undo_id,))
        
        return f"Undo success: restored order #{order_id} to current"

    def show_waiting_orders(self):
        rows = self.conn.execute("SELECT * FROM orders WHERE status = 'WAITING' ORDER BY order_id ASC").fetchall()
        return [
            Order(
                order_id=r["order_id"],
                user=r["user"],
                restaurant=r["restaurant"],
                items=json.loads(r["items"])
            ).to_dict()
            for r in rows
        ]

    def show_completed_orders(self, restaurant: str = None):
        query = "SELECT * FROM orders WHERE status = 'COMPLETED'"
        params = ()
        if restaurant:
            query += " AND restaurant = ?"
            params = (restaurant,)
        query += " ORDER BY completion_seq ASC"
        
        rows = self.conn.execute(query, params).fetchall()
        return [
            {
                "order_id": r["order_id"],
                "user": r["user"],
                "restaurant": r["restaurant"],
                "items": json.loads(r["items"]),
                "note": r["note"],
            }
            for r in rows
        ]

    def requeue_current_order(self):
        with self.conn:
            cur = self.conn.execute("SELECT order_id FROM orders WHERE status = 'CURRENT'").fetchone()
            if not cur:
                return "No current order to requeue"
            
            # Since waiting queue is ordered by order_id, setting it back to WAITING 
            # will naturally restore it exactly to its previous place in the queue.
            self.conn.execute("UPDATE orders SET status = 'WAITING' WHERE order_id = ?", (cur["order_id"],))
            return f"Order #{cur['order_id']} requeued"

    def get_waiting_count(self):
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM orders WHERE status = 'WAITING'").fetchone()
        return row["cnt"]

    def cancel_waiting_order(self, order_id: int):
        with self.conn:
            cur = self.conn.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if not cur:
                return f"Order #{order_id} does not exist"
            if cur["status"] != "WAITING":
                return f"Cannot cancel order #{order_id}: status is {cur['status']}"
            
            self.conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE order_id = ?", (order_id,))
            return f"Order #{order_id} cancelled"

    def export_orders(self, file_path: str):
        rows = self.conn.execute("SELECT * FROM orders ORDER BY order_id ASC").fetchall()
        export_data = []
        for r in rows:
            export_data.append({
                "order_id": r["order_id"],
                "user": r["user"],
                "restaurant": r["restaurant"],
                "items": json.loads(r["items"]),
                "status": r["status"],
                "note": r["note"],
            })
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return f"Exported {len(export_data)} orders to {file_path}"


# ----------------------
# 3 minimal test samples
# ----------------------
if __name__ == "__main__":
    print("=== Test 1: Normal flow ===")
    s1 = DeliveryOrderSystem()
    print(s1.place_order("Alice", "Sushi Bar", ["Sushi", "Miso Soup"]))
    print(s1.place_order("Bob", "Pizza House", ["Pepperoni Pizza"]))
    print("Waiting:", s1.show_waiting_orders())
    print(s1.dispatch_next_order())
    print(s1.complete_current_order("Delivered on time"))
    print("Completed:", s1.show_completed_orders())
    print("Waiting:", s1.show_waiting_orders())

    print("\n=== Test 2: Boundary conditions ===")
    s2 = DeliveryOrderSystem()
    print(s2.dispatch_next_order())
    print(s2.complete_current_order("Nothing to complete"))
    print(s2.undo_last_completion())
    print("Waiting:", s2.show_waiting_orders())
    print("Completed:", s2.show_completed_orders())

    print("\n=== Test 3: Undo last completion rule ===")
    s3 = DeliveryOrderSystem()
    print(s3.place_order("Cindy", "Burger Town", ["Burger"]))
    print(s3.dispatch_next_order())
    print(s3.complete_current_order("Left at door"))
    print("Completed before undo:", s3.show_completed_orders())
    print(s3.undo_last_completion())
    print("Completed after undo:", s3.show_completed_orders())
    print("Current order after undo:", s3.current_order)
    print(s3.undo_last_completion())

    print("\n=== Test 4: Extended Features ===")
    s4 = DeliveryOrderSystem()
    s4.place_order("David", "Sushi Bar", ["Sashimi", "Cola"])
    order_id_eve = int(s4.place_order("Eve", "Pizza House", ["Cheese Pizza"]).split("#")[1].split()[0])
    s4.place_order("Frank", "Sushi Bar", ["Udon Noodle"])
    
    print("Waiting count:", s4.get_waiting_count())
    print("Cancel order Eve:", s4.cancel_waiting_order(order_id_eve))
    print("Cancel already cancelled:", s4.cancel_waiting_order(order_id_eve))
    
    s4.dispatch_next_order()  # Dispatches David
    print("Requeue David:", s4.requeue_current_order())
    print("Requeue no order:", s4.requeue_current_order())
    
    # David is back in waiting, dispatch him again
    s4.dispatch_next_order()
    s4.complete_current_order("Leave at lobby")
    
    s4.dispatch_next_order()  # Dispatches Frank (since Eve was cancelled)
    s4.complete_current_order("Hand delivered")
    
    print("Completed from Sushi Bar only:", s4.show_completed_orders(restaurant="Sushi Bar"))
    print("Exporting:", s4.export_orders("orders_export.json"))
    

    print("\n=== Time Complexity ===")
    print("place_order: SQLite Insert O(1)")
    print("dispatch_next_order: SQLite Select Limit 1 O(1)")
    print("complete_current_order: SQLite Update + Insert O(1)")
    print("undo_last_completion: SQLite Update + Delete O(1)")
    print("show_waiting_orders: SQLite Select O(n)")
    print("show_completed_orders: SQLite Select O(m)")
