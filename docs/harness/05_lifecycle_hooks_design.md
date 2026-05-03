# 优化点 05: 确定性生命周期钩子体系

> **版本**: v2.0 (已落地实现)
> **创建日期**: 2026-05-03
> **实现日期**: 2026-05-03
> **优先级**: 中
> **状态**: ✅ 已完成
> **依赖**: 01_session_event_stream_design, 02_harness_sandbox_decoupling_design
> **参考来源**: Harness Engineering "确定性生命周期钩子"

---

## 实现状态

### ✅ 已完成模块

| 模块 | 文件 | 实现状态 |
|------|------|----------|
| **LifecycleHookRegistry** | `src/lifecycle_hooks.py` | ✅ 已实现，含完整 API |
| **内置钩子** | `src/builtin_hooks.py` | ✅ 已实现，覆盖所有节点 |
| **Harness 集成** | `src/harness.py` | ✅ 已集成，带钩子触发 |
| **AgentLoop 集成** | `src/agent_loop.py` | ✅ 已集成，自动初始化 |
| **测试** | `tests/test_lifecycle_hooks.py` | ✅ 已实现，覆盖所有功能 |

### 关键变更

1. **统一注册体系**: 所有钩子通过 `LifecycleHookRegistry` 集中管理
2. **优先级执行**: 钩子按优先级顺序执行（数值越小越先执行）
3. **执行统计**: 每个钩子有完整的调用统计（次数、成功率、耗时）
4. **失败处理**: 钩子失败不中断主流程，可选 fail_fast 模式
5. **内置钩子**: 会话、工具、LLM、响应、上下文等全生命周期覆盖

---

## 落地架构

### 钩子注册体系

```python
class LifecycleHookRegistry:
    """确定性生命周期钩子注册中心"""

    # === 注册 ===
    def register(hook_point, callback, priority=0, name=None) -> str
    def unregister(hook_id) -> bool
    def clear_hooks(hook_point=None) -> int

    # === 触发 ===
    async def trigger(hook_point, context, fail_fast=False) -> HookTriggerReport
    def trigger_sync(hook_point, context) -> HookTriggerReport

    # === 查询 ===
    def list_hooks(hook_point=None) -> list[dict]
    def get_hook_stats(hook_id) -> dict
    def get_all_stats() -> dict
    def get_hook_count(hook_point=None) -> int
    def has_hook(hook_id) -> bool
```

### 钩子节点定义

```python
class HookPoint(str, Enum):
    """钩子节点枚举"""

    # 会话生命周期 (4个)
    SESSION_START = "session_start"          # 会话开始
    SESSION_END = "session_end"              # 会话结束
    SESSION_PAUSE = "session_pause"          # 会话暂停
    SESSION_RESUME = "session_resume"        # 会话恢复

    # 工具执行生命周期 (3个)
    TOOL_CALL_BEFORE = "tool_call_before"    # 工具调用前
    TOOL_CALL_AFTER = "tool_call_after"      # 工具调用后
    TOOL_CALL_ERROR = "tool_call_error"      # 工具调用错误

    # LLM 调用生命周期 (5个)
    LLM_CALL_BEFORE = "llm_call_before"      # LLM 调用前
    LLM_CALL_AFTER = "llm_call_after"        # LLM 调用后
    LLM_STREAM_START = "llm_stream_start"    # 流式开始
    LLM_STREAM_CHUNK = "llm_stream_chunk"    # 流式块
    LLM_STREAM_END = "llm_stream_end"        # 流式结束

    # 响应生命周期 (2个)
    RESPONSE_BEFORE = "response_before"      # 响应生成前
    RESPONSE_AFTER = "response_after"        # 响应生成后

    # 上下文生命周期 (3个)
    CONTEXT_RESET_BEFORE = "context_reset_before"
    CONTEXT_RESET_AFTER = "context_reset_after"
    SUMMARY_GENERATED = "summary_generated"

    # 子代理生命周期 (4个)
    SUBAGENT_SPAWN = "subagent_spawn"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_END = "subagent_end"
    SUBAGENT_ERROR = "subagent_error"

    # Ralph Loop 生命周期 (4个)
    RALPH_ITERATION_START = "ralph_iteration_start"
    RALPH_ITERATION_END = "ralph_iteration_end"
    RALPH_COMPLETION_CHECK = "ralph_completion_check"
    RALPH_CONTEXT_RESET = "ralph_context_reset"
```

### 内置钩子实现

| 钩子节点 | 钩子名称 | 功能 |
|----------|----------|------|
| `session_start` | `session_log_start` | 记录会话开始日志 |
| `session_start` | `session_init_state` | 初始化会话状态 |
| `session_end` | `session_log_end` | 记录会话结束日志 |
| `session_end` | `session_persist_state` | 持久化会话状态 |
| `tool_call_before` | `tool_permission_check` | 检查工具权限 |
| `tool_call_before` | `tool_log_call` | 记录工具调用日志 |
| `tool_call_before` | `tool_path_mapping` | Sandbox 路径映射 |
| `tool_call_after` | `tool_validate_result` | 验证工具结果 |
| `tool_call_after` | `tool_log_result` | 记录工具结果日志 |
| `tool_call_error` | `tool_log_error` | 记录工具错误日志 |
| `llm_call_before` | `llm_log_call` | 记录 LLM 调用日志 |
| `llm_call_before` | `llm_context_check` | 检查上下文大小 |
| `llm_call_after` | `llm_validate_response` | 验证 LLM 响应 |
| `llm_call_after` | `llm_log_response` | 记录 LLM 响应日志 |
| `response_before` | `response_log_prepare` | 记录响应准备日志 |
| `response_after` | `response_update_state` | 更新响应状态 |
| `response_after` | `response_check_completion` | 检查是否完成 |
| `context_reset_before` | `context_log_reset` | 记录上下文重置 |
| `context_reset_before` | `context_extract_critical` | 提取关键上下文 |
| `summary_generated` | `summary_log` | 记录摘要生成 |
| `subagent_spawn` | `subagent_log_spawn` | 记录子代理创建 |
| `subagent_end` | `subagent_log_end` | 记录子代理结束 |
| `ralph_iteration_end` | `ralph_persist_state` | 持久化 Ralph 状态 |

---

## Harness 集成

### 钩子触发流程

```python
class Harness:
    """Harness 控制器 - 带生命周期钩子"""

    def __init__(self, ..., hook_registry=None):
        self._hook_registry = hook_registry
        self._hook_reports = []

    async def _trigger_hook(hook_point, context) -> HookTriggerReport:
        """触发生命周期钩子"""
        if not self._hook_registry:
            return None
        report = await self._hook_registry.trigger(hook_point, context)
        self._hook_reports.append(report)
        return report

    async def run_cycle(priority) -> CycleResult:
        """执行一轮对话循环（带钩子）"""
        # 1. 构建 context
        context = self._build_context_from_session()

        # 2. llm_call_before 钩子
        await self._trigger_hook(HookPoint.LLM_CALL_BEFORE, {...})

        # 3. response_before 钩子
        await self._trigger_hook(HookPoint.RESPONSE_BEFORE, {...})

        # 4. LLM 推理
        response = await self.llm_client.reason(context, tools)

        # 5. llm_call_after 钩子
        await self._trigger_hook(HookPoint.LLM_CALL_AFTER, {...})

        # 6. 处理工具调用
        if message.get("tool_calls"):
            # 7. _route_tool_calls_with_hooks
            results = await self._route_tool_calls_with_hooks(tool_calls)

        # 8. response_after 钩子
        await self._trigger_hook(HookPoint.RESPONSE_AFTER, {...})

        return cycle_result

    async def run_conversation(initial_prompt) -> str:
        """执行完整对话（带钩子）"""
        # 1. session_start 钩子
        await self._trigger_hook(HookPoint.SESSION_START, {...})

        # 2. 循环执行
        try:
            while iteration < self.max_iterations:
                cycle_result = await self.run_cycle(priority)
                if not cycle_result["continue_loop"]:
                    break

            # 3. session_end 钩子（成功）
            await self._trigger_hook(HookPoint.SESSION_END, {...})
            return final_response

        except Exception as e:
            # session_end 钩子（错误）
            await self._trigger_hook(HookPoint.SESSION_END, {...})
            raise

    async def _execute_single_tool_with_hooks(tool_call) -> dict:
        """执行单个工具（带钩子）"""
        # 1. tool_call_before 钩子
        await self._trigger_hook(HookPoint.TOOL_CALL_BEFORE, {...})

        # 2. 执行工具
        result = await self.sandbox.execute_tools([tool_call])

        # 3. tool_call_after 钩子
        await self._trigger_hook(HookPoint.TOOL_CALL_AFTER, {...})

        return result
```

---

## AgentLoop 集成

```python
class AgentLoop:
    """Agent 主循环 - 带生命周期钩子"""

    def __init__(
        self,
        gateway,
        ...
        hook_registry=None,           # 可选注入钩子注册中心
        enable_builtin_hooks=True,    # 默认启用内置钩子
    ):
        # === 生命周期钩子 ===
        self._hook_registry = hook_registry or get_global_registry()
        if enable_builtin_hooks and self._hook_registry.get_hook_count() == 0:
            register_builtin_hooks(self._hook_registry)

        # === 初始化 Harness（传递钩子）===
        self.harness = Harness(
            llm_client=self.llm_client,
            session=self.session,
            sandbox=self.sandbox,
            hook_registry=self._hook_registry,
        )

    def get_hook_registry(self) -> LifecycleHookRegistry:
        """获取钩子注册中心"""
        return self._hook_registry

    def get_hook_stats(self) -> dict:
        """获取钩子执行统计"""
        return self._hook_registry.get_all_stats()

    def register_custom_hook(hook_point, callback, priority=100, name=None) -> str:
        """注册自定义钩子"""
        return self._hook_registry.register(hook_point, callback, priority, name)
```

---

## 自定义钩子注册

```python
from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry
from src.agent_loop import AgentLoop

# 方式 1: 通过 AgentLoop 注册
agent = AgentLoop(gateway)
agent.register_custom_hook(
    HookPoint.TOOL_CALL_BEFORE,
    my_custom_check,
    priority=50,  # 在内置钩子之后执行
    name="my_check"
)

# 方式 2: 直接操作注册中心
registry = agent.get_hook_registry()
registry.register(
    HookPoint.RESPONSE_AFTER,
    my_response_handler,
    priority=0,
    name="response_handler"
)

# 方式 3: 全局注册中心
from src.lifecycle_hooks import get_global_registry
from src.builtin_hooks import register_builtin_hooks

registry = get_global_registry()
register_builtin_hooks(registry)  # 注册内置钩子
registry.register(HookPoint.SESSION_START, my_session_init, priority=-1)
```

---

## 测试验证

### 测试覆盖

| 测试类 | 覆盖功能 |
|--------|----------|
| `TestLifecycleHookRegistryInit` | 初始化、钩子节点定义 |
| `TestHookRegistration` | 注册、注销、优先级排序 |
| `TestHookTrigger` | 同步/异步触发、失败处理 |
| `TestHookStats` | 统计更新、成功率计算 |
| `TestHookQueries` | 查询方法、列表、计数 |
| `TestBuiltinHooks` | 内置钩子注册、执行验证 |
| `TestGlobalRegistry` | 全局注册中心管理 |

### 验证标准

1. **注册/注销正确**: `register()` 返回 hook_id，`unregister()` 成功移除
2. **优先级排序**: 钩子按 priority 升序执行
3. **触发正确**: `trigger()` 返回完整执行报告
4. **统计更新**: 成功/失败调用计数正确
5. **失败处理**: 钩子失败不中断主流程
6. **内置钩子**: 覆盖所有关键节点

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **流程自动化增强** | 关键节点自动执行预设动作 |
| **钩子可扩展** | 动态注册自定义钩子 |
| **优先级管理** | 钩子按优先级有序执行 |
| **执行统计** | 钩子执行次数/成功/失败统计 |
| **失败处理** | 钩子失败不中断主流程 |
| **确定性执行** | 不依赖模型记忆，系统确保执行 |

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流
- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Harness 集成
- [src/lifecycle_hooks.py](../src/lifecycle_hooks.py) - 钩子注册中心实现
- [src/builtin_hooks.py](../src/builtin_hooks.py) - 内置钩子定义
- [tests/test_lifecycle_hooks.py](../tests/test_lifecycle_hooks.py) - 测试文件