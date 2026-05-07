"""
内置生命周期钩子定义

基于 Harness Engineering "确定性生命周期钩子" 设计：
- 在关键节点自动触发预设动作
- 由系统确保关键流程被执行
- 不依赖可能被模型遗忘的指令

钩子分类：
1. 会话生命周期钩子：session_start, session_end
2. 工具执行钩子：tool_call_before, tool_call_after
3. LLM 调用钩子：llm_call_before, llm_call_after
4. 响应钩子：response_before, response_after
5. 上下文钩子：context_reset_before, context_reset_after
6. 子代理钩子：subagent_spawn, subagent_end
7. Ralph Loop 钩子：ralph_iteration_start, ralph_iteration_end

模块拆分：
- _session_hooks.py: 会话生命周期 + 上下文钩子
- _tool_hooks.py: 工具执行 + 子代理钩子
- _llm_hooks.py: LLM 调用钩子
- _response_hooks.py: 响应 + Ralph Loop 钩子
"""

import logging
from collections.abc import Callable
from typing import Any

from src._llm_hooks import register_llm_hooks
from src._response_hooks import register_ralph_hooks, register_response_hooks
from src._session_hooks import register_context_hooks, register_session_hooks
from src._tool_hooks import register_subagent_hooks, register_tool_hooks
from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry

logger = logging.getLogger(__name__)


def register_builtin_hooks(registry: LifecycleHookRegistry) -> None:
    """注册所有内置钩子

    Args:
        registry: 钩子注册中心实例
    """
    # === 会话生命周期钩子 ===
    register_session_hooks(registry)

    # === 上下文钩子 ===
    register_context_hooks(registry)

    # === 工具执行钩子 ===
    register_tool_hooks(registry)

    # === 子代理钩子 ===
    register_subagent_hooks(registry)

    # === LLM 调用钩子 ===
    register_llm_hooks(registry)

    # === 响应钩子 ===
    register_response_hooks(registry)

    # === Ralph Loop 钩子 ===
    register_ralph_hooks(registry)

    logger.info(f"Builtin hooks registered: total={registry.get_hook_count()}")


# === 自定义钩子注册辅助 ===


def register_custom_hook(
    registry: LifecycleHookRegistry,
    hook_point: HookPoint,
    callback: Callable[..., Any],
    priority: int = 100,
    name: str | None = None,
) -> str:
    """注册自定义钩子

    Args:
        registry: 钩子注册中心
        hook_point: 钩子节点
        callback: 钩子回调
        priority: 优先级（默认 100，在内置钩子之后执行）
        name: 钩子名称

    Returns:
        hook_id: 钩子唯一标识
    """
    result = registry.register(hook_point, callback, priority=priority, name=name)
    # 当直接传入 callback 时，返回的是 str (hook_id)
    return result if isinstance(result, str) else callback.__name__


def create_hook_context(**kwargs) -> dict[str, Any]:
    """创建钩子上下文

    Args:
        **kwargs: 上下文参数

    Returns:
        钩子上下文字典
    """
    return kwargs


# === 公开 API ===

__all__ = [
    "create_hook_context",
    "register_builtin_hooks",
    "register_custom_hook",
]