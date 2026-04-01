from collections import deque
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
    def __init__(self):
        # Waiting orders must use deque for O(1) popleft.
        self.waiting_orders = deque()
        self.current_order = None
        # Completed history is append-only list.
        self.completed_orders = []
        # Undo stack stores only completion actions for single-step rollback.
        self.undo_stack = []
        self.next_order_id = 1

    def place_order(self, user, restaurant, items):
        order = Order(
            order_id=self.next_order_id,
            user=user,
            restaurant=restaurant,
            items=list(items),
        )
        self.next_order_id += 1
        self.waiting_orders.append(order)
        return f"Order placed: #{order.order_id} for {user}"

    def dispatch_next_order(self):
        if self.current_order is not None:
            return (
                f"Cannot dispatch: current order #{self.current_order.order_id} is not completed yet"
            )

        if not self.waiting_orders:
            return "No waiting orders to dispatch"

        self.current_order = self.waiting_orders.popleft()
        return f"Dispatched order #{self.current_order.order_id}"

    def complete_current_order(self, note):
        if self.current_order is None:
            return "No current order to complete"

        completion_record = {
            "order": self.current_order,
            "note": note,
        }
        self.completed_orders.append(completion_record)
        self.undo_stack.append(completion_record)
        done_id = self.current_order.order_id
        self.current_order = None
        return f"Completed order #{done_id}"

    def undo_last_completion(self):
        if not self.undo_stack:
            return "No completion record to undo"

        if self.current_order is not None:
            return (
                f"Cannot undo now: current order #{self.current_order.order_id} is in progress"
            )

        last = self.undo_stack.pop()
        # completed_orders is append-only by design, so the last completed record
        # must match the undo stack top.
        self.completed_orders.pop()
        self.current_order = last["order"]
        return f"Undo success: restored order #{self.current_order.order_id} to current"

    def show_waiting_orders(self):
        if not self.waiting_orders:
            return []

        return [order.to_dict() for order in self.waiting_orders]

    def show_completed_orders(self):
        if not self.completed_orders:
            return []

        return [
            {
                "order_id": record["order"].order_id,
                "user": record["order"].user,
                "restaurant": record["order"].restaurant,
                "items": record["order"].items,
                "note": record["note"],
            }
            for record in self.completed_orders
        ]


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

    print("\n=== Time Complexity ===")
    print("place_order: O(1) amortized")
    print("dispatch_next_order: O(1)")
    print("complete_current_order: O(1) amortized")
    print("undo_last_completion: O(1)")
    print("show_waiting_orders: O(n)  (n = waiting order count)")
    print("show_completed_orders: O(m) (m = completed order count)")
