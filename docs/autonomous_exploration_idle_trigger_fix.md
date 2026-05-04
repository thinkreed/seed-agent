# Autonomous Exploration Idle Trigger Fix - 实施记录

## 问题概述

用户报告：两小时空闲触发的自主探索（Autonomous Exploration）未能正常执行完成。

日志显示：
```
2026-05-04 11:24:40,815 | WARNING | Autonomous explorer started
...
2026-05-04 13:24:43,254 | WARNING | Idle for 120.0 minutes, starting autonomous exploration
```

空闲检测成功触发，但自主探索任务未能正常执行完成。

---

## 根因分析

### 核心问题：`wait_for_user=True` 导致阻塞

**关键发现**：在 `autonomous.py` 第489行：

```python
response = await self.agent.run(next_prompt)
```

`AgentLoop.run()` 方法使用默认参数 `wait_for_user=True`。

**问题机制**：
1. 自主探索调用 `agent.run(next_prompt)` 使用默认参数
2. 若 LLM 在自主探索中调用 `ask_user` 工具
3. `agent.run()` 会**阻塞等待用户响应**
4. 自主模式下无用户在场，无法响应
5. 任务**无限期阻塞**

### 次要问题

1. **缺少超时保护**：单次 `agent.run()` 调用没有超时限制
2. **异常处理不完整**：仅捕获特定异常类型，遗漏 `TimeoutError` 等
3. **调试信息不足**：内部执行缺少详细日志

---

## 实施方案

### Fix 1: Autonomous Mode 标志（主要修复）

**架构设计**：在 Harness 和 AgentLoop 中添加 `autonomous_mode` 标志。

**机制**：
- `autonomous_mode=True` 时，自动跳过 `ask_user` 工具调用
- 返回配置化的默认响应继续执行
- 不阻塞等待用户输入

**修改位置**：
- `src/harness.py`:
  - `__init__()` 添加 `autonomous_mode` 和 `ask_user_skip_response` 参数
  - `run_cycle()` 在检测到 Ask User 时，自动跳过并返回默认响应
  - `set_autonomous_mode()` 方法

- `src/agent_loop.py`:
  - `set_autonomous_mode()` 方法传递给 Harness

- `src/autonomous.py`:
  - `_execute_autonomous_task()` 启用 autonomous_mode
  - `finally` 块恢复正常模式

### Fix 2: 超时保护

**机制**：使用 `asyncio.wait_for()` 包装 LLM 调用。

**配置**：
```python
@dataclass
class AutonomousConfig:
    llm_call_timeout_seconds: int = 300  # 5分钟超时
```

### Fix 3: 异常处理扩展

**扩展捕获范围**：
- `asyncio.TimeoutError` - LLM 调用超时
- `KeyError` - 响应解析失败
- `Exception` - 所有未预期异常

### Fix 4: 错误恢复退避

**机制**：连续失败后等待再重试（指数退避）。

**配置**：
```python
@dataclass
class AutonomousConfig:
    consecutive_failure_threshold: int = 3  # 连续失败阈值
    backoff_duration_seconds: int = 60  # 退避等待时间
    max_backoff_multiplier: int = 5  # 最大退避倍数
```

### Fix 5: 调试日志

**机制**：配置化的详细日志记录。

**配置**：
```python
@dataclass
class AutonomousConfig:
    debug_logging_enabled: bool = True
```

---

## 配置扩展

### AutonomousConfig 新增字段

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `llm_call_timeout_seconds` | 300 | LLM 单次调用超时（5分钟） |
| `iteration_timeout_seconds` | 600 | 单轮迭代总超时（10分钟） |
| `ask_user_skip_response` | `[AUTONOMOUS_SKIP]...` | 自主模式跳过响应 |
| `ask_user_auto_confirm` | `True` | 自动确认用户询问 |
| `consecutive_failure_threshold` | 3 | 连续失败阈值 |
| `backoff_duration_seconds` | 60 | 退避等待时间 |
| `max_backoff_multiplier` | 5 | 最大退避倍数 |
| `debug_logging_enabled` | `True` | 启用调试日志 |

---

## 测试验证

### 新增测试类

| 类名 | 覆盖场景 |
|------|----------|
| `TestAutonomousMode` | autonomous_mode 启用/禁用、配置验证 |
| `TestTimeoutProtection` | 超时配置可用性、错误处理 |
| `TestErrorRecovery` | 退避配置、指数退避计算 |

### 测试结果

```
tests/test_autonomous.py: 43 passed in 0.25s
tests/test_agent_loop.py: 38 passed in 1.86s
```

---

## 关键代码变更

### harness.py - Ask User 自主模式处理

```python
# 检测到 Ask User 时
if pending_request:
    # 自主模式：自动跳过
    if self.autonomous_mode:
        logger.info(f"Autonomous mode: skipping ask_user request {pending_request.request_id}")
        clear_ask_user_state()
        # 记录跳过事件
        self.session.emit_event(EventType.USER_RESPONSE, {
            "autonomous_skip": True,
            "skip_reason": "autonomous_mode",
        })
        # 修改工具结果为跳过响应
        for result in tool_results:
            if result.get("tool_call_id") == first_tool_call_id:
                result["content"] = self._ask_user_skip_response
        # 继续执行循环（而非等待）
        return {"status": "continue", ...}
    # 正常模式：等待用户响应
    ...
```

### autonomous.py - Ralph Loop 增强

```python
async def _run_ralph_loop(self) -> str | None:
    # 从配置读取参数
    autonomous_config = get_autonomous_config()
    llm_timeout = autonomous_config.llm_call_timeout_seconds

    while True:
        # LLM 调用（带超时保护）
        try:
            response = await asyncio.wait_for(
                self.agent.run(next_prompt, wait_for_user=False),
                timeout=llm_timeout,
            )
            consecutive_failures = 0
        except asyncio.TimeoutError:
            logger.warning(f"LLM call timeout ({llm_timeout}s)")
            consecutive_failures += 1
            response = "[TIMEOUT]..."
        except Exception as e:
            consecutive_failures += 1
            response = f"Error: {type(e).__name__}"

        # 错误恢复退避
        if consecutive_failures >= failure_threshold:
            backoff = min(
                backoff_duration * (2 ** (consecutive_failures - failure_threshold)),
                max_backoff,
            )
            await asyncio.sleep(backoff)
```

---

## 总结

**核心修复**：添加 `autonomous_mode` 标志，自动跳过 Ask User 阻塞。

**增强特性**：
- LLM 调用超时保护（5分钟）
- 异常处理扩展（捕获所有异常）
- 错误恢复退避（指数增长，上限5分钟）
- 详细调试日志（配置化启用）

**测试覆盖**：新增 6 个测试用例，全部通过。

---

## 附录：关键文件位置

| 文件 | 关键位置 | 功能 |
|------|---------|------|
| `src/autonomous.py` | `_execute_autonomous_task()` | 启用 autonomous_mode |
| `src/autonomous.py` | `_run_ralph_loop()` | 超时保护 + 退避策略 |
| `src/harness.py` | `run_cycle()` | Ask User 自主模式处理 |
| `src/harness.py` | `set_autonomous_mode()` | 模式切换方法 |
| `src/agent_loop.py` | `set_autonomous_mode()` | 传递给 Harness |
| `src/shared_config.py` | `AutonomousConfig` | 新增配置字段 |
| `tests/test_autonomous.py` | `TestAutonomousMode` | 新增测试类 |