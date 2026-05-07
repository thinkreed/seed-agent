"""
Harness 生命周期钩子模块

聚合层：提供钩子触发函数和上下文构建辅助函数的统一导出。

内容:
- trigger_hook: 触发生命周期钩子
- build_*_ctx: 从 lifecycle_ctx 子模块导出的上下文构建函数
"""

from typing import Any

# 从子模块导入所有上下文构建函数，保持向后兼容
from src.harness.lifecycle_ctx import (
    build_llm_call_after_ctx,
    build_llm_call_before_ctx,
    build_response_after_ctx,
    build_response_before_ctx,
    build_session_end_ctx,
    build_session_start_ctx,
    build_tool_call_after_ctx,
    build_tool_call_before_ctx,
    build_tool_call_error_ctx,
)
from src.lifecycle_hooks import HookPoint, HookTriggerReport, LifecycleHookRegistry


async def trigger_hook(
    hook_registry: LifecycleHookRegistry | None,
    hook_point: HookPoint,
    context: dict[str, Any],
) -> HookTriggerReport | None:
    """触发生命周期钩子

    Args:
        hook_registry: 钩子注册中心（可为 None）
        hook_point: 钩子节点
        context: 钩子上下文

    Returns:
        钩子执行报告（如果没有注册钩子则返回 None）
    """
    if not hook_registry:
        return None

    return await hook_registry.trigger(hook_point, context)


# 公开 API
__all__ = [
    # 触发函数
    "trigger_hook",
    # Session hooks
    "build_session_start_ctx",
    "build_session_end_ctx",
    # LLM hooks
    "build_llm_call_before_ctx",
    "build_llm_call_after_ctx",
    # Response hooks
    "build_response_before_ctx",
    "build_response_after_ctx",
    # Tool hooks
    "build_tool_call_before_ctx",
    "build_tool_call_after_ctx",
    "build_tool_call_error_ctx",
]