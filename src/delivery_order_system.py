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
                CREATE TABLE IF NOT EXISTS operation_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    action TEXT,
                    order_id INTEGER,
                    details TEXT
                );
            ''')

    def _log_operation(self, action: str, order_id: int = None, details: str = ""):
        self.conn.execute(
            "INSERT INTO operation_logs (action, order_id, details) VALUES (?, ?, ?)",
            (action, order_id, details)
        )

    def place_order(self, user, restaurant, items):
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO orders (user, restaurant, items, status) VALUES (?, ?, ?, 'WAITING')",
                (user, restaurant, json.dumps(list(items)))
            )
            order_id = cursor.lastrowid
            self._log_operation("PLACE_ORDER", order_id, f"User: {user}, Restaurant: {restaurant}")
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
            self._log_operation("DISPATCH_ORDER", order_id)
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
            self._log_operation("COMPLETE_ORDER", order_id, f"Note: {note}")
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
            self._log_operation("UNDO_COMPLETION", order_id)
        
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
            
            self.conn.execute("UPDATE orders SET status = 'WAITING' WHERE order_id = ?", (cur["order_id"],))
            self._log_operation("REQUEUE_ORDER", cur["order_id"])
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
            self._log_operation("CANCEL_ORDER", order_id)
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

    def export_operation_logs(self, file_path: str):
        rows = self.conn.execute("SELECT * FROM operation_logs ORDER BY log_id ASC").fetchall()
        logs = []
        for r in rows:
            logs.append({
                "log_id": r["log_id"],
                "timestamp": r["timestamp"],
                "action": r["action"],
                "order_id": r["order_id"],
                "details": r["details"]
            })
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        return f"Exported {len(logs)} operation logs to {file_path}"

