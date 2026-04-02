import os
import sys

# 将项目根目录或 src 添加到 Python 路径（如果需要直接运行）
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.delivery_order_system import DeliveryOrderSystem

def main():
    print("=== 外卖订单派发系统初始化 ===")
    # 指定一个本地文件数据库
    db_path = "delivery_orders.db"
    system = DeliveryOrderSystem(db_path)
    
    print("\n--- 1. 模拟下单 ---")
    print(system.place_order("Alice", "Pizza House", ["Margarita Pizza", "Cola"]))
    print(system.place_order("Bob", "Sushi Bar", ["Salmon Roll", "Miso Soup"]))
    
    print(f"当前等待中的订单数: {system.get_waiting_count()}")
    
    print("\n--- 2. 模拟派单 ---")
    print(system.dispatch_next_order())
    
    print("\n--- 3. 模拟完成 ---")
    print(system.complete_current_order("顺利送达"))
    
    print("\n--- 4. 模拟撤销 ---")
    print(system.undo_last_completion())
    
    print("\n--- 此后可以查看操作日志 ---")
    system.export_operation_logs("logs.json")
    print("写入完成: logs.json")

if __name__ == "__main__":
    main()
