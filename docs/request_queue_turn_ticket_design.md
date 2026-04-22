# Request Queue Turn-Ticket 设计文档

> 版本: 1.0
> 创建日期: 2026-04-22
> 状态: **已实现** (2026-04-22)

---

## 目录

1. [问题背景](#1-问题背景)
2. [设计目标](#2-设计目标)
3. [核心设计](#3-核心设计)
4. [并发控制](#4-并发控制)
5. [CRITICAL 独立队列](#5-critical-独立队列)
6. [动态超时机制](#6-动态超时机制)
7. [错误处理](#7-错误处理)
8. [数据结构设计](#8-数据结构设计)
9. [配置系统](#9-配置系统)
10. [迁移方案](#10-迁移方案)
11. [测试计划](#11-测试计划)
12. [监控与运维](#12-监控与运维)

---

## 1. 问题背景

### 1.1 当前架构问题

当前 `RequestQueue` 采用"执行+存储"模式：

```python
# 当前 request_queue.py
RequestItem:
    result: Dict           # 存储执行结果
    _completion_event: Event  # 等待完成信号

队列调度器:
    取出请求 → 执行请求 → 存储结果 → 触发事件 → 调用者收到结果
```

**核心矛盾**：

| 请求类型 | 当前处理 | 问题 |
|---------|---------|------|
| 非流式请求 | 入队 → 执行 → 存储结果 | ✅ 可行 |
| **流式请求** | 无法入队，使用 workaround | ❌ AsyncGenerator 无法存储 |

**当前的 hacky workaround**：

```python
# client.py - LOW 优先级流式请求的处理
if priority == RequestPriority.LOW:
    # 提交一个空请求排队等轮次
    request_id = await self.submit_to_queue(model_id, 
        [{"role": "user", "content": "__wait_for_queue_slot__"}], priority)
    await self.wait_for_queue_result(request_id)  # 等待轮次到了
    # 然后才开始真正的流式执行
    async for chunk in self._stream_execute_with_rate_limit(...):
        yield chunk
```

**问题本质**：队列设计是"等待结果"模式，流式输出是"订阅过程"模式，两者不兼容。

### 1.2 设计动机

1. **流式请求真正入队**：所有请求（包括流式）都能排队等待
2. **统一入口**：消除 workaround，简化代码
3. **CRITICAL 也排队**：用户交互请求也能排队，但优先级最高
4. **动态调整**：根据实际负载智能调整配置

---

## 2. 设计目标

### 2.1 功能目标

| 目标 | 描述 |
|------|------|
| 流式入队 | 流式请求能像非流式一样排队等待轮次 |
| CRITICAL 独立 | CRITICAL 请求有独立队列，最高优先级 |
| 统一入口 | 所有请求使用相同的入队流程 |
| 调用者控制 | 流式 generator 由调用者迭代，调度器不介入 |
| 动态调整 | 根据负载自动调整容量、速率、超时 |

### 2.2 非功能目标

| 目标 | 描述 |
|------|------|
| 低延迟 | CRITICAL 队列目标等待时间 < 5秒 |
| 高吞吐 | 普通队列支持高负载场景 |
| 可监控 | 提供详细的队列状态和统计信息 |
| 可配置 | 所有关键参数可配置 |
| 可恢复 | 支持取消、超时、队列满等异常处理 |

---

## 3. 核心设计

### 3.1 方案概述：轮次票（TurnTicket）模式

**核心理念**：队列只管"轮次分配"，不介入执行细节。

```
┌─────────────────────────────────────────────────────────────────┐
│                     RequestQueue 职责边界                        │
├─────────────────────────────────────────────────────────────────┤
│  ✅ 负责：                                                       │
│     - 优先级排序（谁先执行）                                      │
│     - 轮次等待机制（什么时候轮到我）                              │
│     - 反压控制（队列满时拒绝）                                    │
│     - 统计收集（等待时间、拒绝率等）                              │
│                                                                 │
│  ❌ 不负责：                                                      │
│     - 执行请求（交给调用者）                                      │
│     - 存储结果（非流式由调用者处理）                              │
│     - 流式输出（由调用者迭代 AsyncGenerator）                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 流程对比

#### 当前架构流程

```
调用者                      队列调度器
   │                           │
   │ submit_to_queue()         │
   │ ──────────────────────>   │
   │                           │ 取出请求
   │                           │ 执行请求
   │                           │ 存储结果
   │ wait_for_result()         │
   │ ──────────────────────>   │
   │                           │ 触发 event
   │   await event.wait()      │
   │ <──────────────────────   │
   │ 收到 result               │
```

#### 新架构流程（TurnTicket）

```
调用者                      队列调度器
   │                           │
   │ request_turn()            │ 发轮次票
   │ ──────────────────────>   │
   │ 收到 ticket               │
   │                           │
   │ await ticket.wait()       │ 取出 ticket
   │   (排队等待)              │ signal_turn()
   │                           │
   │ <──────────────────────   │ 通知：轮次到了
   │                           │
   │ 自己执行请求              │ (调度器不介入)
   │ async with semaphore:     │
   │   await rate_limiter      │
   │   result = await execute  │
   │ 或                        │
   │   async for chunk:        │
   │     yield chunk           │
```

### 3.3 核心变化

| 方面 | 当前 | 新设计 |
|------|------|--------|
| 入队 | `submit()` 返回 `request_id` | `request_turn()` 返回 `TurnTicket` |
| 等待 | `wait_for_result()` 等待结果 | `ticket.wait_for_turn()` 等待轮次 |
| 执行 | 调度器执行 | 调用者执行 |
| 流式 | workaround（空请求占位） | 真正入队，返回 generator |
| 结果存储 | `RequestItem.result` | 调用者自己处理 |

---

## 4. 并发控制

### 4.1 三阶段等待设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           请求处理三阶段                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  阶段1：排队入场 (Turn Assignment)                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ RequestQueue.request_turn(priority)                                  │   │
│  │     ↓                                                               │   │
│  │ TurnTicket.wait_for_turn(timeout)                                   │   │
│  │     ↓                                                               │   │
│  │ 状态：turn_assigned                                                 │   │
│  │ 含义："你有资格进入执行区了，按优先级排序"                          │   │
│  │                                                                     │   │
│  │ 控制器：RequestQueue（优先级队列）                                  │   │
│  │ 不感知并发数，只管优先级排序                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  阶段2：抢执行位置 (Concurrent Acquisition)                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ async with semaphore:                                               │   │
│  │     ↓                                                               │   │
│  │ 状态：concurrent_acquired                                           │   │
│  │ 含义："你现在可以真正执行了，拿到并发许可"                          │   │
│  │                                                                     │   │
│  │ 控制器：asyncio.Semaphore（并发数限制）                             │   │
│  │ 与队列独立，不知道优先级                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  阶段3：限流检查 (Rate Limit Acquisition)                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ rate_limiter.acquire()                                              │   │
│  │     ↓                                                               │   │
│  │ 状态：rate_limit_acquired                                           │   │
│  │ 含义："你现在可以发起 API 调用了，拿到限流许可"                     │   │
│  │                                                                     │   │
│  │ 控制器：RateLimiter（Token Bucket + Rolling Window）               │   │
│  │ 与队列和 semaphore 都独立                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  阶段4：执行 (Execution)                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ _execute_with_fallback(...)                                         │   │
│  │     ↓                                                               │   │
│  │ 返回结果或 yield chunks                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 控制器职责边界

| 控制器 | 职责 | 知道什么 | 不知道什么 |
|--------|------|----------|------------|
| **RequestQueue** | 优先级排序 | 当前队列填充率、ticket 状态 | 并发数、限流状态、执行结果 |
| **Semaphore** | 并发数限制 | 当前并发数 | 优先级、队列状态、限流状态 |
| **RateLimiter** | 速率限制 | Token 数量、窗口请求数 | 优先级、并发数、队列状态 |

**核心原则**：三者完全独立，不协调，各司其职。

### 4.3 为什么选择分离独立模式

| 方案 | 描述 | 优点 | 缺点 | 选择 |
|------|------|------|------|------|
| C-1 智能分配 | 队列感知并发，控制轮次分配节奏 | 轮次与执行匹配 | 队列复杂，易出错 | ❌ |
| **C-2 分离独立** | 队列、Semaphore、RateLimiter 各司其职 | 简单清晰，职责分明 | 拿到轮次≠执行 | ✅ |
| C-3 合并控制 | 队列直接控制并发，替代 semaphore | 轮次=并发许可 | 队列复杂，易出错 | ❌ |

### 4.4 调用者视角

```python
async def chat_completion(self, model_id, messages, priority, **kwargs):
    """非流式请求"""
    
    # 阶段1：排队入场
    ticket = await self._request_queue.request_turn(priority)
    await ticket.wait_for_turn(timeout=timeout)
    logger.debug(f"Ticket {ticket.id}: turn assigned")
    
    # 阶段2：抢执行位置
    async with self._request_semaphore:
        logger.debug(f"Ticket {ticket.id}: concurrent acquired")
        
        # 阶段3：限流检查
        await self._rate_limiter.acquire()
        logger.debug(f"Ticket {ticket.id}: rate limit acquired")
        
        # 阶段4：执行
        result = await self._execute_with_fallback(model_id, messages, **kwargs)
    
    return result

async def stream_chat_completion(self, model_id, messages, priority, **kwargs):
    """流式请求"""
    
    # 阶段1：排队入场
    ticket = await self._request_queue.request_turn(priority)
    await ticket.wait_for_turn(timeout=timeout)
    
    # 阶段2-4：返回 generator（调度器不介入）
    async def actual_stream():
        async with self._request_semaphore:
            await self._rate_limiter.acquire()
            async for chunk in self._stream_with_fallback(model_id, messages, **kwargs):
                yield chunk
    
    return actual_stream()  # 调用者自己迭代
```

---

## 5. CRITICAL 独立队列

### 5.1 队列架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RequestQueue 架构                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ CRITICAL 队列（独立）                                                  │ │
│  │                                                                       │ │
│  │ 特性：                                                                 │ │
│  │ - 独立容量：critical_max_size                                         │ │
│  │ - 独立反压：critical_backpressure_threshold                           │ │
│  │ - 最高优先级：调度器最先处理                                          │ │
│  │ - 独立调度速率：critical_dispatch_rate                                │ │
│  │                                                                       │ │
│  │ 用途：用户直接交互请求                                                │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 普通队列（HIGH / NORMAL / LOW）                                       │ │
│  │                                                                       │ │
│  │ 特性：                                                                 │ │
│  │ - 共享容量：normal_max_size                                           │ │
│  │ - 共享反压：normal_backpressure_threshold                             │ │
│  │ - 按优先级排序：HIGH > NORMAL > LOW                                   │ │
│  │                                                                       │ │
│  │ 用途：RalphLoop、Subagent、后台任务                                   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ 调度器                                                                 │ │
│  │                                                                       │ │
│  │ 分配顺序：                                                             │ │
│  │ 1. CRITICAL 队列 → 有就先处理                                         │ │
│  │ 2. HIGH 队列 → CRITICAL 空，处理 HIGH                                │ │
│  │ 3. NORMAL 队列 → HIGH 空，处理 NORMAL                                │ │
│  │ 4. LOW 队列 → 其他都空，处理 LOW                                      │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 配置参数

| 参数 | 默认值 | 描述 |
|------|--------|------|
| `critical_max_size` | 10 | CRITICAL 队列最大容量 |
| `critical_backpressure_threshold` | 0.9 | CRITICAL 反压阈值（较高，允许更多排队） |
| `critical_dispatch_rate` | 10.0 | CRITICAL 调度速率（req/sec，较快） |
| `critical_target_wait_time` | 5.0 | CRITICAL 目标平均等待时间（秒） |
| `normal_max_size` | 50 | HIGH/NORMAL/LOW 共享容量 |
| `normal_backpressure_threshold` | 0.8 | 普通队列反压阈值 |
| `normal_dispatch_rate` | 0.33 | 普通队列调度速率（req/sec） |
| `normal_target_wait_time` | 30.0 | 普通队列目标平均等待时间（秒） |

### 5.3 调度逻辑

```python
async def _dispatch_loop(self):
    """调度循环：CRITICAL 优先"""
    while self._running:
        await self._new_request_event.wait()
        
        # 1. 先处理 CRITICAL（最高优先级）
        ticket = await self._pop_ticket(RequestPriority.CRITICAL)
        if ticket:
            ticket.signal_turn()
            self._stats.record_signal(RequestPriority.CRITICAL)
            await asyncio.sleep(1.0 / self.config.critical_dispatch_rate)
            continue
        
        # 2. CRITICAL 空，处理普通队列（按优先级）
        for priority in [RequestPriority.HIGH, RequestPriority.NORMAL, RequestPriority.LOW]:
            ticket = await self._pop_ticket(priority)
            if ticket:
                ticket.signal_turn()
                self._stats.record_signal(priority)
                await asyncio.sleep(1.0 / self.config.normal_dispatch_rate)
                break
        
        # 3. 所有队列都空，清除事件
        if not await self._has_pending_tickets():
            self._new_request_event.clear()
```

### 5.4 智能容量和反压调整

根据实际运行情况，自动调整配置：

```python
async def _adjust_config(self):
    """根据统计数据智能调整配置"""
    
    # 1. CRITICAL 队列调整
    critical_avg_wait = self._stats.get_avg_wait_time(RequestPriority.CRITICAL)
    critical_p95_wait = self._stats.get_p95_wait_time(RequestPriority.CRITICAL)
    
    # 如果 CRITICAL 平均等待超过目标，增加调度速率
    if critical_avg_wait > self.config.critical_target_wait_time:
        self.config.critical_dispatch_rate *= 1.2
        logger.info(
            f"Auto-adjust: CRITICAL dispatch_rate increased to "
            f"{self.config.critical_dispatch_rate:.2f}"
        )
        
        # 如果 P95 很高，增加容量
        if critical_p95_wait > self.config.critical_target_wait_time * 2:
            self.config.critical_max_size = min(
                self.config.critical_max_size + 5,
                30  # 最大不超过 30
            )
    
    # 2. 反压阈值调整（根据拒绝率）
    critical_reject_rate = (
        self._stats.rejected[RequestPriority.CRITICAL] / 
        max(1, self._stats.submitted[RequestPriority.CRITICAL])
    )
    
    if critical_reject_rate > 0.1:  # 拒绝率超过 10%
        self.config.critical_backpressure_threshold = min(
            self.config.critical_backpressure_threshold + 0.05,
            0.95
        )
```

---

## 6. 动态超时机制

### 6.1 基础超时配置

| 优先级 | 基础超时 | 描述 |
|--------|---------|------|
| CRITICAL | 30 秒 | 用户交互，不能等太久 |
| HIGH | 60 秒 | RalphLoop 迭代 |
| NORMAL | 120 秒 | Subagent 任务 |
| LOW | 300 秒 | 后台任务，可以等很久 |

### 6.2 动态调整逻辑

根据系统负载动态调整超时：

```
负载因子 vs 超时倍数

超时倍数
    │
2.0 ┤                     ●●●●●  (高负载：超时延长)
    │                  ●●●
    │               ●●
    │            ●●
1.0 ┤─────────●──────────────────  (正常负载：基础超时)
    │       ●
    │     ●
    │   ●
0.5 ┤●●●                       (低负载：超时缩短)
    │
    └─────────────────────────── 负载因子
        0.0    0.7    0.8    0.9    1.0
               ↑
          load_factor_threshold
```

```python
def get_timeout(self, priority: RequestPriority, load_factor: float) -> float:
    """获取动态超时"""
    base = self.base_timeouts[priority]
    
    if load_factor > self.load_factor_threshold:
        # 高负载：延长超时，给更多等待时间
        multiplier = 1.0 + (load_factor - self.load_factor_threshold) * 1.5
        multiplier = min(multiplier, self.max_multiplier)  # 最大 2.0
    else:
        # 低负载：缩短超时，快速处理或快速失败
        multiplier = 1.0 - (self.load_factor_threshold - load_factor) * 0.5
        multiplier = max(multiplier, self.min_multiplier)  # 最小 0.5
    
    return base * multiplier
```

### 6.3 负载因子计算

```python
def get_load_factor(self) -> float:
    """计算当前负载因子"""
    # 负载因子 = 队列填充率 + 并发使用率 + 限流窗口使用率
    
    queue_fill = self._request_queue.get_total_fill_ratio()
    
    # Semaphore 使用率（通过追踪活跃请求数估算）
    # 需要在 gateway 中追踪 _active_count
    
    rate_limit_status = self.get_rate_limit_status()
    window_usage = rate_limit_status.window_usage_ratio if rate_limit_status else 0.0
    
    # 综合负载因子
    load_factor = (queue_fill * 0.4 + window_usage * 0.6)
    return load_factor
```

---

## 7. 错误处理

### 7.1 错误类型矩阵

| 错误类型 | 发生阶段 | 触发条件 | 影响 | 处理策略 |
|---------|---------|---------|------|---------|
| **QueueFullError** | 申请轮次 | 填充率 >= threshold | 新请求被拒绝 | 抛出异常，返回错误 |
| **TurnWaitTimeout** | 等待轮次 | 排队太久，未分配轮次 | 调用者放弃 | 抛出异常，记录等待时间 |
| **RateLimitError** | 限流检查 | Token bucket 空太久 | 调用者放弃 | 抛出异常，可重试 |
| **CancelledError** | 任意阶段 | 用户中断/任务取消 | 停止等待 | 清理资源，释放 ticket |
| **APIConnectionError** | 执行阶段 | API 错误/网络问题 | 结果失败 | 降级到 fallback provider |

### 7.2 QueueFullError

```python
class QueueFullError(Exception):
    """队列已满，拒绝新请求"""
    
    def __init__(self, fill_ratio: float, threshold: float, queue_type: str):
        self.fill_ratio = fill_ratio
        self.threshold = threshold
        self.queue_type = queue_type
        super().__init__(
            f"Queue ({queue_type}) at {fill_ratio:.1%} capacity "
            f"(threshold: {threshold:.1%}), rejecting requests"
        )
```

**调用者处理**：

```python
async def chat_completion(self, ...):
    try:
        ticket = await self._queue.request_turn(priority)
        await ticket.wait_for_turn(timeout)
        ...
    except QueueFullError as e:
        # 根据优先级决定处理方式
        if priority == RequestPriority.CRITICAL:
            raise UserFacingError("System busy, please try again")
        else:
            raise SubagentQueueFullError(...)
```

### 7.3 TurnWaitTimeout

```python
class TurnWaitTimeout(Exception):
    """轮次等待超时"""
    
    def __init__(self, ticket_id: str, waited_seconds: float, queue_status: dict):
        self.ticket_id = ticket_id
        self.waited_seconds = waited_seconds
        self.queue_status = queue_status
        super().__init__(
            f"Ticket {ticket_id} waited {waited_seconds}s for turn, "
            f"queue status: {queue_status}"
        )
```

**不同优先级的处理策略**：

| 优先级 | 超时处理 |
|--------|---------|
| CRITICAL | 返回用户友好提示："系统繁忙，请稍后再试" |
| HIGH | RalphLoop 跳过本轮迭代，继续下一轮 |
| NORMAL | Subagent 标记任务失败，返回错误 |
| LOW | 后台任务放弃，记录日志 |

### 7.4 主动取消

```python
class TurnTicket:
    
    def cancel(self, reason: str = "User cancelled"):
        """取消排队"""
        self._cancelled = True
        self._cancel_reason = reason
        self._turn_event.set()  # 唤醒等待者，让其抛出 CancelledError

class RequestQueue:
    
    async def cancel_ticket(self, ticket_id: str, reason: str) -> bool:
        """取消指定的 ticket"""
        async with self._lock:
            # 从所有队列中查找并移除
            ...
            ticket.cancel(reason)
            return True
```

**调用场景**：

```python
# 场景1：用户中断
class AgentLoop:
    def interrupt(self, user_input: str):
        if self._current_ticket:
            self._queue.cancel_ticket(
                self._current_ticket.id, 
                "User interrupted"
            )

# 场景2：RalphLoop 停止
class RalphLoop:
    def stop(self):
        self._is_running = False
        if self._current_ticket:
            self._queue.cancel_ticket(
                self._current_ticket.id, 
                "RalphLoop stopped"
            )

# 场景3：Subagent 终止
class SubagentManager:
    async def kill_subagent(self, task_id: str):
        if instance._current_ticket:
            self._queue.cancel_ticket(instance._current_ticket.id, ...)
```

### 7.5 错误处理流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        请求处理流程 + 错误分支                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  request_turn()                                                     │
│      │                                                              │
│      ├─ [队列满] ─→ QueueFullError                                  │
│      │              ├─ CRITICAL ─→ 返回用户友好提示                  │
│      │              └─ 其他 ─→ 标记失败                              │
│      │                                                              │
│      ↓ (成功获得 ticket)                                            │
│                                                                     │
│  wait_for_turn(timeout)                                             │
│      │                                                              │
│      ├─ [超时] ─→ TurnWaitTimeout                                   │
│      │              ├─ CRITICAL ─→ 返回用户提示                      │
│      │              ├─ HIGH ─→ RalphLoop 跳过本轮                   │
│      │              └─ NORMAL/LOW ─→ 标记失败                        │
│      │                                                              │
│      ├─ [取消] ─→ CancelledError ─→ 清理资源                        │
│      │                                                              │
│      ↓ (轮次已分配)                                                  │
│                                                                     │
│  async with semaphore                                               │
│      ↓                                                              │
│  rate_limiter.acquire()                                             │
│      │                                                              │
│      ├─ [超时] ─→ RateLimitError ─→ 重试或返回                      │
│      │                                                              │
│      ↓                                                              │
│  execute()                                                          │
│      │                                                              │
│      ├─ [连接错误] ─→ 重试 + fallback                               │
│      ├─ [API错误] ─→ 降级到 fallback provider                       │
│      │                                                              │
│      ↓ (成功)                                                       │
│                                                                     │
│  return result / yield chunks                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. 数据结构设计

### 8.1 TurnTicket

```python
@dataclass
class TurnTicket:
    """轮次票 - 代表"轮到你执行了"的信号"""
    
    # 基本信息
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: RequestPriority
    created_at: float = field(default_factory=time.time)
    
    # 轮次信号
    _turn_event: asyncio.Event = field(default_factory=asyncio.Event)
    _turn_time: Optional[float] = None
    _cancelled: bool = False
    _cancel_reason: Optional[str] = None
    
    # 状态追踪（可选）
    state: Optional[RequestState] = None
    
    async def wait_for_turn(self, timeout: float) -> None:
        """等待轮次到达"""
        try:
            await asyncio.wait_for(self._turn_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise TurnWaitTimeout(self.id, timeout, {})
        
        if self._cancelled:
            raise asyncio.CancelledError(self._cancel_reason)
    
    def signal_turn(self) -> None:
        """调度器通知：轮次到了"""
        self._turn_time = time.time()
        self._turn_event.set()
    
    def cancel(self, reason: str) -> None:
        """取消排队"""
        self._cancelled = True
        self._cancel_reason = reason
        self._turn_event.set()
    
    def get_wait_duration(self) -> float:
        """获取等待时长"""
        if self._turn_time:
            return self._turn_time - self.created_at
        return time.time() - self.created_at
```

### 8.2 QueueConfig

```python
class QueueConfig:
    """队列配置（可动态调整）"""
    
    # CRITICAL 队列配置
    critical_max_size: int = 10
    critical_backpressure_threshold: float = 0.9
    critical_dispatch_rate: float = 10.0
    critical_target_wait_time: float = 5.0
    
    # 普通队列配置
    normal_max_size: int = 50
    normal_backpressure_threshold: float = 0.8
    normal_dispatch_rate: float = 0.33
    normal_target_wait_time: float = 30.0
    
    # 自动调整
    auto_adjust_enabled: bool = True
```

### 8.3 TimeoutConfig

```python
class TimeoutConfig:
    """等待超时配置（可动态调整）"""
    
    # 基础超时
    base_timeouts: Dict[RequestPriority, float] = {
        RequestPriority.CRITICAL: 30.0,
        RequestPriority.HIGH: 60.0,
        RequestPriority.NORMAL: 120.0,
        RequestPriority.LOW: 300.0,
    }
    
    # 动态调整参数
    auto_adjust_enabled: bool = True
    load_factor_threshold: float = 0.7
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0
    
    def get_timeout(self, priority: RequestPriority, load_factor: float) -> float:
        """获取动态超时"""
        ...
```

### 8.4 QueueStats

```python
class QueueStats:
    """队列统计（用于智能调整和监控）"""
    
    # 等待时间记录
    wait_times: Dict[RequestPriority, List[float]]
    
    # 计数
    submitted: Dict[RequestPriority, int]
    signaled: Dict[RequestPriority, int]
    rejected: Dict[RequestPriority, int]
    
    def record_submit(self, priority: RequestPriority):
        self.submitted[priority] += 1
    
    def record_signal(self, priority: RequestPriority):
        self.signaled[priority] += 1
    
    def record_rejected(self, priority: RequestPriority):
        self.rejected[priority] += 1
    
    def record_wait_time(self, priority: RequestPriority, duration: float):
        self.wait_times[priority].append(duration)
    
    def get_avg_wait_time(self, priority: RequestPriority) -> float:
        ...
    
    def get_p95_wait_time(self, priority: RequestPriority) -> float:
        ...
```

### 8.5 RequestState（可选，用于详细监控）

```python
class RequestState:
    """请求状态追踪"""
    
    phase: str = "created"
    # created → queued → turn_assigned → concurrent_waiting → 
    # concurrent_acquired → rate_limit_waiting → rate_limit_acquired → 
    # executing → completed
    
    # 时间戳
    created_at: float
    queued_at: float
    turn_assigned_at: Optional[float] = None
    concurrent_acquired_at: Optional[float] = None
    execution_started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # 耗时
    queue_wait_duration: Optional[float] = None
    concurrent_wait_duration: Optional[float] = None
    execution_duration: Optional[float] = None
    
    def transition_to(self, phase: str):
        """状态转换"""
        ...
```

---

## 9. 配置系统

### 9.1 默认配置值

```python
DEFAULT_QUEUE_CONFIG = {
    "critical_max_size": 10,
    "critical_backpressure_threshold": 0.9,
    "critical_dispatch_rate": 10.0,
    "critical_target_wait_time": 5.0,
    
    "normal_max_size": 50,
    "normal_backpressure_threshold": 0.8,
    "normal_dispatch_rate": 0.33,
    "normal_target_wait_time": 30.0,
    
    "auto_adjust_enabled": True,
}

DEFAULT_TIMEOUT_CONFIG = {
    "critical_base_timeout": 30.0,
    "high_base_timeout": 60.0,
    "normal_base_timeout": 120.0,
    "low_base_timeout": 300.0,
    
    "auto_adjust_enabled": True,
    "load_factor_threshold": 0.7,
    "min_multiplier": 0.5,
    "max_multiplier": 2.0,
}
```

### 9.2 配置文件格式

在现有 `config/config.json` 中新增 `queue` 和 `timeout` 配置块：

```json
{
  "models": { ... },
  "agents": { ... },
  
  "queue": {
    "critical_max_size": 10,
    "critical_backpressure_threshold": 0.9,
    "critical_dispatch_rate": 10.0,
    "normal_max_size": 50,
    "normal_backpressure_threshold": 0.8,
    "normal_dispatch_rate": 0.33,
    "auto_adjust_enabled": true,
    "critical_target_wait_time": 5.0,
    "normal_target_wait_time": 30.0
  },
  
  "timeout": {
    "critical_base_timeout": 30.0,
    "high_base_timeout": 60.0,
    "normal_base_timeout": 120.0,
    "low_base_timeout": 300.0,
    "auto_adjust_enabled": true,
    "load_factor_threshold": 0.7
  }
}
```

### 9.3 配置加载

```python
# models.py 中新增配置类

class QueueConfigModel(BaseModel):
    critical_max_size: int = 10
    critical_backpressure_threshold: float = 0.9
    critical_dispatch_rate: float = 10.0
    critical_target_wait_time: float = 5.0
    
    normal_max_size: int = 50
    normal_backpressure_threshold: float = 0.8
    normal_dispatch_rate: float = 0.33
    normal_target_wait_time: float = 30.0
    
    auto_adjust_enabled: bool = True

class TimeoutConfigModel(BaseModel):
    critical_base_timeout: float = 30.0
    high_base_timeout: float = 60.0
    normal_base_timeout: float = 120.0
    low_base_timeout: float = 300.0
    
    auto_adjust_enabled: bool = True
    load_factor_threshold: float = 0.7
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0

class FullConfig(BaseModel):
    models: Dict[str, ProviderConfig]
    agents: Dict[str, AgentConfig]
    queue: Optional[QueueConfigModel] = None
    timeout: Optional[TimeoutConfigModel] = None
```

---

## 10. 迁移方案

### 10.1 全量迁移策略

一次性完成迁移，不保留旧模式：

```
Step 1: 准备新数据结构
├── 新增 TurnTicket 类
├── 新增 QueueConfig、TimeoutConfig 类
├── 新增 QueueStats 类
└── 新增 RequestState 类（可选）

Step 2: 重写 RequestQueue
├── 删除 submit()、wait_for_result()、_execute_request()
├── 删除 RequestItem 类
├── 实现 request_turn()、cancel_ticket()
├── 实现 CRITICAL 独立队列逻辑
├── 实现智能调整逻辑
└── 实现统计收集

Step 3: 重写 LLMGateway
├── 删除 submit_to_queue()、wait_for_queue_result()
├── 删除 stream_chat_completion 中的 placeholder workaround
├── 实现 chat_completion（三阶段等待）
├── 实现 stream_chat_completion（排队 + generator）
├── 实现动态超时计算
└── 实现负载因子计算

Step 4: 配置加载
├── models.py 新增 QueueConfigModel、TimeoutConfigModel
├── config/config.json 新增配置块
└── LLMGateway 初始化时加载配置

Step 5: 测试验证
├── 单元测试
├── 集成测试
├── 性能测试
└── 功能测试
```

### 10.2 需要删除的代码

| 文件 | 删除内容 |
|------|---------|
| `request_queue.py` | `RequestItem` 类、`submit()`、`wait_for_result()`、`_execute_request()` |
| `client.py` | `submit_to_queue()`、`wait_for_queue_result()`、placeholder workaround |

### 10.3 不需要修改的代码

| 文件 | 原因 |
|------|------|
| `agent_loop.py` | 调用 gateway.chat_completion()，接口不变 |
| `ralph_loop.py` | 调用 agent.run()，无感知变化 |
| `subagent.py` | 调用 gateway.chat_completion()，接口不变 |
| `subagent_manager.py` | 调用 run_subagent()，无感知变化 |
| `rate_limiter.py` | 独立限流逻辑，不涉及队列 |
| `scheduler.py` | 通过 AgentLoop 间接调用，无感知变化 |

### 10.4 文件改动清单

| 文件 | 改动类型 | 改动内容 |
|------|---------|---------|
| `src/request_queue.py` | **重写** | 全新 TurnTicket 模式实现 |
| `src/client.py` | **修改** | 三阶段等待、动态超时 |
| `src/models.py` | **新增** | QueueConfigModel、TimeoutConfigModel |
| `config/config.json` | **修改** | 新增 queue、timeout 配置块 |
| `src/agent_loop.py` | 无修改 | - |
| `src/ralph_loop.py` | 无修改 | - |
| `src/subagent.py` | 无修改 | - |
| `src/subagent_manager.py` | 无修改 | - |

---

## 11. 测试计划

### 11.1 单元测试

| 测试模块 | 测试项 | 验证点 |
|---------|--------|--------|
| **TurnTicket** | `wait_for_turn` 正常 | 事件触发后返回 |
| | `wait_for_turn` 超时 | 抛出 TurnWaitTimeout |
| | `cancel` 取消 | 抛出 CancelledError |
| | `signal_turn` 通知 | 事件被设置 |
| **RequestQueue** | `request_turn` 正常 | 返回 ticket，入队成功 |
| | `request_turn` 队列满 | 抛出 QueueFullError |
| | `_dispatch_loop` 多优先级 | 按优先级顺序分配 |
| | `cancel_ticket` 存在 | 成功取消 |
| | `cancel_ticket` 不存在 | 返回 False |
| | CRITICAL 独立队列 | 独立容量、独立反压 |
| **QueueConfig** | 智能调整 | 根据等待时间调整 |
| **TimeoutConfig** | 动态超时 | 根据负载调整 |

### 11.2 集成测试

| 测试场景 | 验证点 |
|---------|--------|
| **CRITICAL 请求流程** | 优先级最高，快速响应 |
| **HIGH 请求流程** | RalphLoop 正常等待 |
| **NORMAL 请求流程** | Subagent 正常等待 |
| **LOW 请求流程** | 后台任务正常等待 |
| **流式请求流程** | 能排队，能流式输出 |
| **并发场景** | 多请求同时入队，优先级排序正确 |
| **取消场景** | 用户中断，正确取消并清理 |
| **降级场景** | Provider 失败，自动 fallback |

### 11.3 性能测试

| 测试项 | 场景 | 验证点 |
|--------|------|--------|
| **高负载** | 100+ 请求入队 | 队列稳定，反压生效 |
| **长时间运行** | 8小时持续请求 | 无资源泄漏 |
| **并发上限** | maxConcurrent=5 | 实际并发不超过5 |
| **CRITICAL 延迟** | 高负载场景 | CRITICAL 平均等待 < 10秒 |
| **智能调整** | 持续高负载 | 配置自动调整生效 |

### 11.4 功能测试

| 测试项 | 验证点 |
|--------|--------|
| **AgentLoop 用户交互** | CRITICAL 请求正常处理 |
| **RalphLoop 长周期** | HIGH 请求正常迭代 |
| **Subagent 并行** | 多个 NORMAL 请求并行执行 |
| **Scheduler 后台任务** | LOW 请求正常入队 |
| **流式输出完整性** | 所有 chunks 正确 yield |
| **错误恢复** | 超时、取消后正常恢复 |

---

## 12. 监控与运维

### 12.1 监控指标

| 指标 | 描述 | 获取方式 |
|------|------|---------|
| `queue_length` | 各队列长度 | `queue.get_stats()["queue_lengths"]` |
| `fill_ratio` | 队列填充率 | `queue.get_stats()["fill_ratios"]` |
| `avg_wait_time` | 平均等待时间 | `queue.get_stats()["stats"]["avg_wait_times"]` |
| `p95_wait_time` | P95 等待时间 | `queue.get_stats()["stats"]["p95_wait_times"]` |
| `reject_rate` | 拒绝率 | `rejected / submitted` |
| `throughput` | 吞吐量 | `signaled / 时间窗口` |

### 12.2 监控告警规则

| 告警 | 条件 | 处理 |
|------|------|------|
| CRITICAL 延迟过高 | avg_wait_time > 10s | 检查系统负载，调整配置 |
| CRITICAL 拒绝率高 | reject_rate > 5% | 增加 critical_max_size |
| 普通队列满 | fill_ratio > 0.9 | 检查是否有阻塞 |
| 吞吐量下降 | throughput < 历史平均 | 检查限流状态 |

### 12.3 日志记录

```python
# 关键事件日志

# ticket 创建
logger.debug(f"Ticket {ticket.id} submitted (priority={priority.name})")

# ticket 信号
logger.debug(f"Ticket {ticket.id} signaled (wait_duration={duration:.2f}s)")

# 队列满
logger.warning(f"Queue ({queue_type}) full: fill_ratio={fill_ratio:.1%}")

# 超时
logger.warning(f"Ticket {ticket_id} timeout: waited={waited:.1f}s")

# 取消
logger.info(f"Ticket {ticket_id} cancelled: reason={reason}")

# 智能调整
logger.info(f"Auto-adjust: {param} changed to {new_value}")
```

### 12.4 运维命令

```python
# 查看队列状态
stats = gateway._request_queue.get_stats()

# 动态调整配置
gateway._request_queue.config.critical_max_size = 15

# 取消所有 CRITICAL 请求
await gateway._request_queue.cancel_all_by_priority(RequestPriority.CRITICAL)

# 清空队列
await gateway._request_queue.cancel_all_tickets("Emergency cleanup")
```

---

## 附录

### A. 与现有系统的集成点

| 系统 | 集成方式 | 影响 |
|------|---------|------|
| AgentLoop | 通过 gateway.chat_completion() | 无感知变化 |
| RalphLoop | 通过 agent.run() → gateway | 无感知变化 |
| SubagentManager | 通过 gateway.chat_completion() | 无感知变化 |
| Scheduler | 通过 AgentLoop | 无感知变化 |
| RateLimiter | 三阶段等待的第三阶段 | 独立运作 |
| FallbackChain | 执行阶段使用 | 独立运作 |

### B. 配置参数完整列表

| 参数 | 类型 | 默认值 | 范围 | 描述 |
|------|------|--------|------|------|
| critical_max_size | int | 10 | 5-30 | CRITICAL 队列容量 |
| critical_backpressure_threshold | float | 0.9 | 0.7-0.95 | CRITICAL 反压阈值 |
| critical_dispatch_rate | float | 10.0 | 5-50 | CRITICAL 调度速率 |
| critical_target_wait_time | float | 5.0 | 1-15 | CRITICAL 目标等待时间 |
| normal_max_size | int | 50 | 20-100 | 普通队列容量 |
| normal_backpressure_threshold | float | 0.8 | 0.6-0.9 | 普通队列反压阈值 |
| normal_dispatch_rate | float | 0.33 | 0.1-5 | 普通队列调度速率 |
| normal_target_wait_time | float | 30.0 | 10-60 | 普通队列目标等待时间 |
| auto_adjust_enabled | bool | True | - | 自动调整开关 |
| critical_base_timeout | float | 30.0 | 10-60 | CRITICAL 基础超时 |
| high_base_timeout | float | 60.0 | 30-120 | HIGH 基础超时 |
| normal_base_timeout | float | 120.0 | 60-300 | NORMAL 基础超时 |
| low_base_timeout | float | 300.0 | 120-600 | LOW 基础超时 |
| load_factor_threshold | float | 0.7 | 0.5-0.9 | 负载因子阈值 |
| min_multiplier | float | 0.5 | 0.25-0.75 | 超时最小倍数 |
| max_multiplier | float | 2.0 | 1.5-3.0 | 超时最大倍数 |

### C. 状态机定义

```
TurnTicket 状态：

created ──→ queued ──→ turn_assigned ──→ (交给调用者)
    │          │              │
    │          │              ├─→ cancelled (用户取消)
    │          │              │
    │          └─→ timeout (等待超时)
    │          │
    └─→ cancelled (入队前取消)


RequestState 状态：

created ──→ queued ──→ turn_assigned ──→ concurrent_waiting
    │          │              │              │
    │          │              │              └─→ concurrent_acquired
    │          │              │                      │
    │          │              │                      └─→ rate_limit_waiting
    │          │              │                              │
    │          │              │                              └─→ rate_limit_acquired
    │          │              │                                      │
    │          │              │                                      └─→ executing
    │          │              │                                              │
    │          │              │                                              └─→ completed
    │          │              │
    │          │              ├─→ timeout
    │          │              │
    │          └─→ timeout
    │          │
    │          └─→ cancelled
    │
    └─→ cancelled
```

---

## 参考文档

- [src/request_queue.py](../src/request_queue.py) - 当前队列实现
- [src/client.py](../src/client.py) - LLMGateway
- [src/rate_limiter.py](../src/rate_limiter.py) - 限流器
- [rate_limiting_system_design.md](rate_limiting_system_design.md) - 限流系统设计
- [ralph_loop.md](ralph_loop.md) - Ralph Loop 设计
- [subagents.md](subagents.md) - Subagent 设计