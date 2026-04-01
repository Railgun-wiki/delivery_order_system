# Delivery Order System (外卖订单调度系统)

这是一个基于 Python 和 SQLite 实现的轻量级外卖订单调度分发系统。系统模拟了真实外卖流转中的排队、派发、完成、撤销、取消及重排队等复杂状态机管理，并具备本地数据持久化与一致性保障能力。

## 📑 核心特性 (Features)

*   **全生命周期订单调度**：支持新单入队、FIFO派发订单、标记完成及备注。
*   **状态机溯源与回滚**：专门实现的安全 `Undo` 操作栈，允许单步撤回错点的“完成”状态，同时保障处理一致性。
*   **扩展实用管理接口**：
    *   **订单重排队 (`requeue`)**：应对骑手接单异常，将订单从派送中重置回最初的等待顺序。
    *   **状态统计计算**：毫秒级返回当前系统还在等待的实时订单数。
    *   **等待单软删除 (`cancel`)**：拦截非对应状态的取消请求，允许取消等待中订单。
    *   **特定报表过滤与导出**：支持按“餐厅名称”等条件检索历史结算单据，一键导出 JSON 系统快照。

## 🏗️ 架构设计 (Architecture)

早期版本使用纯内存容器（`deque` 和 `list`）实现，但在扩展需求场景下（如查询聚合、可持久化保存机制）迁移到了内部嵌入式数据库（SQLite）。

这种设计**既消除了部署外部数据库服务的麻烦（支持 `:memory:` 纯内存或本地 `.db` 文件持久化），又获得了高并发下关系型数据库强力的状态锁及复杂的 SQL 报表检索支持**。操作的时间复杂度均被压低至 `O(1)` 或完全利用索引加速。

有关深度详细的状态机流转设计、DTO 解析及选型理由，请参阅：
*   👉 **[详细系统设计文档 (design.md)](design.md)**
*   👉 **[系统架构演化与选型对比 (architecture_comparison.md)](architecture_comparison.md)**

## 🚀 快速开始 (Quick Start)

### 环境要求
*   Python 3.7 或更高版本 (依赖内置的 `sqlite3`、`dataclasses` 和 `json`)
*   无其他第三方环境/库配置要求。

### 接入演示
```python
from delivery_order_system import DeliveryOrderSystem

# 初始化调度系统 (采用内存数据库，也可传入 db_path="app.db" 进行文件持久化)
system = DeliveryOrderSystem(db_path=":memory:")

# 1. 客户下单
order_str = system.place_order("Alice", "Pizza House", ["Cheese Pizza"])
print(order_str)  # Order placed: #1 for Alice

# 2. 系统派单
print(system.dispatch_next_order())  # Dispatched order #1

# 3. 完成与撤回
system.complete_current_order("Delivered successfully")
system.undo_last_completion() # 状态恢复

# 4. 其他操作
system.requeue_current_order()
print("等待单数:", system.get_waiting_count())
```

## 🧪 测试套件 (Testing)

本项目配备了严谨的 `unittest` 自动化测试用例（包括空队列检测、错误行为拦截、底层状态机数量守恒的极度一致性校验等）。该测试与业务逻辑处于完全解耦状态。

在项目根目录下执行以下命令以运行单元测试：

```bash
python -m unittest test_delivery_order_system.py -v
```