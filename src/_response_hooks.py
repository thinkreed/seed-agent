"""
响应钩子

包含：
- 响应钩子：response_before, response_after
- Ralph Loop 钩子：ralph_iteration_start, ralph_iteration_end, ralph_completion_check, ralph_context_reset
"""

import logging
from typing import Any

from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry

logger = logging.getLogger(__name__)


def register_response_hooks(registry: LifecycleHookRegistry) -> None:
    """注册响应钩子"""

    @registry.register(
        HookPoint.RESPONSE_BEFORE, priority=0, name="response_log_prepare"
    )
    def response_log_prepare(context: dict[str, Any]) -> None:
        """记录响应准备"""
        iteration = context.get("iteration", 0)
        max_iterations = context.get("max_iterations", 30)

        logger.debug(f"Preparing response: iteration={iteration}/{max_iterations}")

    @registry.register(
        HookPoint.RESPONSE_AFTER, priority=0, name="response_update_state"
    )
    def response_update_state(context: dict[str, Any]) -> None:
        """更新响应状态"""
        session = context.get("session")
        response = context.get("response")

        if session and response:
            context["last_response"] = response

    @registry.register(
        HookPoint.RESPONSE_AFTER, priority=1, name="response_check_completion"
    )
    def response_check_completion(context: dict[str, Any]) -> None:
        """检查是否完成"""
        response = context.get("response")
        choices = response.get("choices", []) if response else []
        message = choices[0].get("message", {}) if choices else {}

        has_tool_calls = message.get("tool_calls") is not None
        context["should_continue"] = has_tool_calls

    @registry.register(
        HookPoint.RESPONSE_AFTER, priority=2, name="response_metrics_update"
    )
    def response_metrics_update(context: dict[str, Any]) -> None:
        """更新响应指标"""
        harness = context.get("harness")
        metrics = context.get("metrics")

        if harness and metrics and hasattr(harness, "_metrics"):
            harness._metrics.append(metrics)


def register_ralph_hooks(registry: LifecycleHookRegistry) -> None:
    """注册 Ralph Loop 钩子"""

    @registry.register(
        HookPoint.RALPH_ITERATION_START, priority=0, name="ralph_log_iteration"
    )
    def ralph_log_iteration(context: dict[str, Any]) -> None:
        """记录 Ralph 迭代开始"""
        iteration = context.get("iteration", 0)
        max_iterations = context.get("max_iterations", 1000)

        logger.debug(f"Ralph iteration: {iteration}/{max_iterations}")

    @registry.register(
        HookPoint.RALPH_ITERATION_END, priority=0, name="ralph_persist_state"
    )
    def ralph_persist_state(context: dict[str, Any]) -> None:
        """持久化 Ralph 状态"""
        ralph = context.get("ralph_loop")
        response = context.get("response")

        if ralph and hasattr(ralph, "_persist_state"):
            ralph._persist_state(response)

    @registry.register(
        HookPoint.RALPH_COMPLETION_CHECK, priority=0, name="ralph_log_check"
    )
    def ralph_log_check(context: dict[str, Any]) -> None:
        """记录 Ralph 完成检查"""
        completion_type = context.get("completion_type", "unknown")
        criteria = context.get("completion_criteria", {})

        logger.debug(
            f"Ralph completion check: type={completion_type}, criteria={criteria}"
        )

    @registry.register(
        HookPoint.RALPH_CONTEXT_RESET, priority=0, name="ralph_log_reset"
    )
    def ralph_log_reset(context: dict[str, Any]) -> None:
        """记录 Ralph 上下文重置"""
        iteration = context.get("iteration", 0)
        reason = context.get("reason", "periodic")

        logger.info(f"Ralph context reset: iteration={iteration}, reason={reason}")