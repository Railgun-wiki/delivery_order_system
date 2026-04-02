import unittest
import json
import os
import sys

# 添加 src 目录到被引用的路径，以便读取 delivery_order_system
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.delivery_order_system import DeliveryOrderSystem

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
        
        # 测试：取消不存在的订单
        self.assertIn("does not exist", self.system.cancel_waiting_order(999))
        
        # 测试：空状态下重排队
        self.assertEqual(self.system.requeue_current_order(), "No current order to requeue")
        
        self.system.place_order("Alice", "Shop A", ["Item 1"])
        self.system.dispatch_next_order()
        
        # 测试：取消处理中 (CURRENT) 的订单
        self.assertIn("Cannot cancel order #1: status is CURRENT", self.system.cancel_waiting_order(1))
        
        self.system.complete_current_order("Done")
        
        # 测试：取消已完成 (COMPLETED) 的订单
        self.assertIn("Cannot cancel order #1: status is COMPLETED", self.system.cancel_waiting_order(1))

    def test_state_consistency(self):
        """验证数据库层面的状态机一致性保证（任何时刻最多只能有1个CURRENT订单）"""
        for i in range(5):
            self.system.place_order(f"User{i}", "Sushi Bar", ["Sushi"])
            
        def get_current_count():
            return self.system.conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'CURRENT'").fetchone()[0]

        # 初始无CURRENT订单
        self.assertEqual(get_current_count(), 0)
        self.assertEqual(self.system.get_waiting_count(), 5)
        
        # 第一次派发，CURRENT升为1
        self.system.dispatch_next_order()
        self.assertEqual(get_current_count(), 1)
        self.assertEqual(self.system.get_waiting_count(), 4)
        
        # 尝试再次派发，应该被拒绝，验证状态保持一致不出现2个CURRENT
        self.assertIn("Cannot dispatch", self.system.dispatch_next_order())
        self.assertEqual(get_current_count(), 1)
        
        # 完成订单，CURRENT归0
        self.system.complete_current_order("Ok1")
        self.assertEqual(get_current_count(), 0)
        self.assertEqual(len(self.system.show_completed_orders()), 1)
        
        # 撤销，CURRENT重回1
        self.system.undo_last_completion()
        self.assertEqual(get_current_count(), 1)
        self.assertEqual(len(self.system.show_completed_orders()), 0)
        
        # 重排队，CURRENT彻底归0，等待重回5
        self.assertIn("requeued", self.system.requeue_current_order())
        self.assertEqual(get_current_count(), 0)
        self.assertEqual(self.system.get_waiting_count(), 5)
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

    def test_export_operation_logs(self):
        """测试操作日志的录入与快照导出功能"""
        # 放几笔业务操作触发状态变更
        self.system.place_order("Ivan", "Pizza Boss", ["Pizza X"])
        self.system.dispatch_next_order()
        self.system.complete_current_order("Noted")
        self.system.undo_last_completion()
        
        log_file = "test_operation_logs.json"
        
        # 调用暴露的接口测试导出
        out_msg = self.system.export_operation_logs(log_file)
        self.assertIn("Exported 4 operation logs", out_msg)
        
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
            self.assertEqual(len(logs), 4)
            # 依次检查日志行为
            self.assertEqual(logs[0]["action"], "PLACE_ORDER")
            self.assertEqual(logs[1]["action"], "DISPATCH_ORDER")
            self.assertEqual(logs[2]["action"], "COMPLETE_ORDER")
            self.assertEqual(logs[3]["action"], "UNDO_COMPLETION")
            
        os.remove(log_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)