import unittest
import json
import os
from delivery_order_system import DeliveryOrderSystem

class TestDeliveryOrderSystem(unittest.TestCase):
    def setUp(self):
        # 使用内存数据库保证测试的完全隔离与干净
        self.system = DeliveryOrderSystem(db_path=":memory:")

    def test_normal_flow_and_waiting_count(self):
        """测试正常流程：下单 -> 获取等待数量 -> 派发 -> 完成"""
        self.system.place_order("Alice", "Sushi Bar", ["Sushi", "Miso Soup"])
        self.system.place_order("Bob", "Pizza House", ["Pepperoni Pizza"])
        
        self.assertEqual(self.system.get_waiting_count(), 2)
        
        dispatch_msg = self.system.dispatch_next_order()
        self.assertIn("Alice", self.system.current_order.user)
        self.assertIn("#1", dispatch_msg)
        
        cmp_msg = self.system.complete_current_order("Delivered on time")
        self.assertIn("#1", cmp_msg)
        self.assertIsNone(self.system.current_order)
        
        completed = self.system.show_completed_orders()
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["user"], "Alice")
        self.assertEqual(completed[0]["note"], "Delivered on time")
        self.assertEqual(self.system.get_waiting_count(), 1)

    def test_boundary_conditions(self):
        """测试异常流及边界情况返回提示"""
        self.assertEqual(self.system.dispatch_next_order(), "No waiting orders to dispatch")
        self.assertEqual(self.system.complete_current_order("Nothing"), "No current order to complete")
        self.assertEqual(self.system.undo_last_completion(), "No completion record to undo")

    def test_undo_and_requeue_rules(self):
        """测试扩展状态机流转：取消 -> 重排队 -> 新接单 -> 尝试撤销旧单阻止 -> 强制撤销恢复"""
        self.system.place_order("Cindy", "Burger Town", ["Burger"])
        self.system.place_order("David", "KFC", ["Fries"])
        
        self.system.dispatch_next_order() # 分配给 Cindy (#1)
        self.system.complete_current_order("Left at door")
        
        self.system.dispatch_next_order() # 分配给 David (#2)
        
        # David没送完时，试图撤销Cindy的单子 => 应该被拦截
        undo_err = self.system.undo_last_completion()
        self.assertIn("is in progress", undo_err)
        
        # David骑手想重排队 (requeue)
        requeue_msg = self.system.requeue_current_order()
        self.assertIn("requeued", requeue_msg)
        self.assertIsNone(self.system.current_order)
        
        # 此时没有正在派送的订单了，可以合法撤销Cindy的完成记录
        undo_ok = self.system.undo_last_completion()
        self.assertIn("restored order #1", undo_ok)
        self.assertIsNotNone(self.system.current_order)
        self.assertEqual(self.system.current_order.user, "Cindy")
        self.assertEqual(len(self.system.show_completed_orders()), 0)
        
        # 将被撤回的 Cindy 重排队，清空 current_order
        self.system.requeue_current_order()

        # 再撤销就没有记录了
        self.assertEqual(self.system.undo_last_completion(), "No completion record to undo")

    def test_cancel_waiting_order(self):
        """测试在等待中软删除单据的情况"""
        order_id_msg = self.system.place_order("Eve", "Mexican Grill", ["Taco"])
        order_id = int(order_id_msg.split("#")[1].split()[0])
        
        # 成功取消
        self.assertIn("cancelled", self.system.cancel_waiting_order(order_id))
        self.assertEqual(self.system.get_waiting_count(), 0)
        
        # 再次尝试取消已取消的订单
        self.assertIn("status is CANCELLED", self.system.cancel_waiting_order(order_id))

    def test_filter_and_export(self):
        """测试餐厅记录按名过滤与文件快照导出"""
        self.system.place_order("Frank", "BBQ Shop", ["Wings"])
        self.system.place_order("Grace", "BBQ Shop", ["Ribs"])
        self.system.place_order("Heidi", "Salad Bar", ["Salad"])
        
        # 全部分发与完成
        self.system.dispatch_next_order()
        self.system.complete_current_order("Ok1")
        self.system.dispatch_next_order()
        self.system.complete_current_order("Ok2")
        self.system.dispatch_next_order()
        self.system.complete_current_order("Ok3")
        
        bbq_orders = self.system.show_completed_orders(restaurant="BBQ Shop")
        self.assertEqual(len(bbq_orders), 2)
        
        export_file = "test_export_orders.json"
        self.system.export_orders(export_file)
        
        self.assertTrue(os.path.exists(export_file))
        with open(export_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(len(data), 3)
            self.assertEqual(data[-1]["status"], "COMPLETED")
            
        os.remove(export_file) # 清理文件

if __name__ == "__main__":
    unittest.main(verbosity=2)