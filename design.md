# 外卖订单派发系统设计文档 (Delivery Order System)

## 1. 项目目标与最小功能范围
**项目目标**：实现一个模拟的外卖订单派发与调度中心，能够按照先后顺序处理订单，并提供完成及撤销等状态流转支持。
**最小功能范围**：
*   用户下单，系统生成订单并加入等待队列。
*   系统派发等待队列中最先下达的订单（FIFO）。
*   将正在处理中的当前订单标记为已完成，输入完成备注，并存入历史记录。
*   支持单步撤销（Undo），将最近一次由于误操作标记为“已完成”的订单恢复为“当前处理中”状态。
*   支持查询当前仍在等待的订单明细，以及已完成的订单历史。

## 2. 系统状态与操作
订单在系统中的生命周期包含以下基本状态：
*   **WAITING (等待中)**：刚下单的初始状态或被重新排队的状态。
*   **CURRENT (处理中)**：由系统派发，当前唯一正在被处理的订单状态。
*   **COMPLETED (已完成)**：派送完成，记录完成顺序和备注。
*   **CANCELLED (已取消)**：新增的扩展状态，处于等待中的订单被用户手动取消。

操作主要围绕状态机的跃迁：
`WAITING` -> (dispatch) -> `CURRENT` -> (complete) -> `COMPLETED`
`COMPLETED` -> (undo) -> `CURRENT`
`CURRENT` -> (requeue) -> `WAITING`
`WAITING` -> (cancel) -> `CANCELLED`

## 3. 数据结构设计说明
系统经历了从“纯内存结构”到“嵌入式持久化(SQLite)”的演进：

### 数据对象 (DTO)
使用了 Python 的 `@dataclass` 定义了 `Order` 类，对订单进行封装，包含 `order_id`、`user`、`restaurant`、`items` 以及序列化方法 `to_dict()`，保证向外输出的数据表现形式一致。

### 存储结构 (SQLite)
为了支持后期复杂的条件查询、计数以及数据持久化，放弃了初期的 `collections.deque` 和 `list` 栈方案，改用 SQLite 内置内存数据库（可无缝切换为文件）：
1.  **orders 表**：
    *   `order_id`: 主键，自增。自然形成了下单时间的先后顺序。
    *   `status`: 文本枚举 (`WAITING`, `CURRENT`, `COMPLETED`, `CANCELLED`)。
    *   `completion_seq`: 订单完成的具体次序（应对乱序完成和撤销保证正确的历史排序）。
2.  **undo_stack 表**：
    *   单独维护的一个栈结构数据表。其 `undo_id` 构成了自增栈指针。
    *   当订单被 completed 时，将 `order_id` 压入（INSERT）；当撤销时，查询最大的 `undo_id` 对应记录并弹出（DELETE）。

## 4. 核心接口说明
*   `place_order(user, restaurant, items)`: 创建新订单，状态设为 `WAITING`，存入数据库。
*   `dispatch_next_order()`: 从 `orders` 中取出 `status='WAITING'` 且 `order_id` 最小的记录，将状态置为 `CURRENT`（前置检查必须无其他活跃订单）。
*   `complete_current_order(note)`: 将 `CURRENT` 订单标记为 `COMPLETED`，记录备注，顺延 `completion_seq`，并在 `undo_stack` 表中压栈。
*   `undo_last_completion()`: 从 `undo_stack` 弹出最后一次完成记录，将对应的订单状态从 `COMPLETED` 改回 `CURRENT`，清空 `note` 和 `completion_seq`。

## 5. 复杂度分析
底层依托于 SQLite：
*   **place_order**: `O(1)`，执行单条记录的尾部 INSERT。
*   **dispatch_next_order**: `O(1)`，利用主键索引进行 `TOP 1` 的 SELECT 并执行单行 UPDATE。
*   **complete_current_order**: `O(1)`，涉及简单的计数最大值查询和 UPDATE + INSERT。
*   **undo_last_completion**: `O(1)`，查询并删除最大主键记录，并反向 UPDATE。
*   **show_waiting_orders**: `O(N)`，需遍历 N 个等待中的订单并进行 JSON 解析和对象映射。
*   **show_completed_orders**: `O(M)`，遍历 M 个已完成且符合条件的订单。

## 6. 边界情况与测试设计
在设计与代码中，通过 `Test 2` 和 `Test 3` 用例严密校验了如下边界情况：
1.  **空队列派单**：队列无 `WAITING` 订单时调用 `dispatch`，需返回异常提示而不允许崩溃。
2.  **空状态完成**：当前 `CURRENT` 游标为空时调用 `complete`，应拦截。
3.  **空记录撤销**：`undo_stack` 为空时调用 `undo`，须安全提示。
4.  **撤销冲突**：如果在撤销前，系统已经新派发了一个订单（此时有了新的 `CURRENT` 订单），则必须**拒绝撤销**，以免系统同时出现两个派送中的订单造成状态机崩盘。

## 7. 扩展功能说明
为应对外卖业务的实际痛点，在原有核心功能基础上扩展：
1.  **get_waiting_count()**: `O(1)` 直接利用 DBMS 的 `COUNT(*)` 聚合进行等待数量统计。
2.  **cancel_waiting_order(order_id)**: 允许软删除（`CANCELLED`），并拦截对“已开始处理”或“已不存在”订单的非法取消。
3.  **requeue_current_order()**: 应对骑手接错单等情况，将 `CURRENT` 订单状态重置置回 `WAITING`。由于 SQLite 的出队是依旧找 `order_id` 最小的行，这不仅使其回到队列，而且会自动**插队回原本该排的最前面**，完美适配现实逻辑。
4.  **show_completed_orders(restaurant=...)**: 历史记录允许按餐馆名称过滤聚合，适用于商家后台报表。
5.  **export_orders(file_path)**: 将从下单到销毁的完整订单表导出为本地 `.json` 数据快照。

## 8. AI Coding 反思
在系统从“纯内存”向“数据库持久化”演进的过程中有以下体会：
1.  **需求演进的敏捷性**：初始版本为了满足 `collections.deque` 的强约束，写了纯内存结构。但到了后续要求“按餐厅筛选”、“统计数量”、“取消订单”时，如果纯用 deque 会引来极大的遍历开销（如 O(N) 的 list removal）。这印证了：随着业务检索复杂度增加，关系型数据库（哪怕是 SQLite）始终是对业务状态机管理的最佳抽象。
2.  **分离关注点与重构技巧**：在 AI 介入进行 SQLite 重命名与重构时，遵循了“接口契约不变”原则：内部的存储介质彻底颠覆了，但公开暴露的返回格式（字典、字符串）、函数签名完全没有破坏，使得上层测试用例得以 100% 重用。
3.  **通过提示词约束质量**：通过约束“只能包含 1 个 undo 操作”、“必须考虑边界和反例”，使得代码生成的鲁棒性变高；用最小化测试（Minimal Test Samples）能够最高效地验证状态流转在各个边缘分支上没有引发 Bug。这是一个开发、验证与快速修正的闭环。