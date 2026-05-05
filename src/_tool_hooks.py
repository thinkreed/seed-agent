"""
工具执行钩子

包含：
- 工具执行钩子：tool_call_before, tool_call_after, tool_call_error
- 子代理钩子：subagent_spawn, subagent_start, subagent_end, subagent_error
"""

import logging
from typing import Any

from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry

logger = logging.getLogger(__name__)


def register_tool_hooks(registry: LifecycleHookRegistry) -> None:
    """注册工具执行钩子"""

    @registry.register(
        HookPoint.TOOL_CALL_BEFORE, priority=0, name="tool_permission_check"
    )
    def tool_permission_check(context: dict[str, Any]) -> bool:
        """检查工具调用权限"""
        tool_name = context.get("tool_name")
        permission_set = context.get("permission_set")
        sandbox = context.get("sandbox")

        # 如果有 Sandbox，使用 Sandbox 权限检查
        if sandbox and hasattr(sandbox, "_check_permission"):
            tool_args = context.get("tool_args", {})
            if not sandbox._check_permission(tool_name, tool_args):
                raise PermissionError(
                    f"Tool '{tool_name}' not allowed in current sandbox"
                )

        # 如果有权限集，检查工具是否在权限集中
        if permission_set and tool_name:
            if isinstance(permission_set, dict):
                allowed = permission_set.get(tool_name, {}).get("action", "allow")
            elif isinstance(permission_set, (list, set)):
                allowed = tool_name in permission_set
            else:
                allowed = True

            if not allowed:
                raise PermissionError(f"Tool '{tool_name}' not in permission set")

        return True

    @registry.register(HookPoint.TOOL_CALL_BEFORE, priority=1, name="tool_log_call")
    def tool_log_call(context: dict[str, Any]) -> None:
        """记录工具调用"""
        tool_name = context.get("tool_name", "unknown")
        tool_args = context.get("tool_args", {})
        tool_call_id = context.get("tool_call_id", "unknown")
        logger.debug(f"Tool call: {tool_name} (id={tool_call_id}), args={tool_args}")

    @registry.register(HookPoint.TOOL_CALL_BEFORE, priority=2, name="tool_path_mapping")
    def tool_path_mapping(context: dict[str, Any]) -> None:
        """路径映射（如果有 Sandbox）"""
        sandbox = context.get("sandbox")
        tool_args = context.get("tool_args", {})

        if sandbox and hasattr(sandbox, "_map_paths"):
            mapped_args = sandbox._map_paths(tool_args)
            context["mapped_args"] = mapped_args

    @registry.register(
        HookPoint.TOOL_CALL_AFTER, priority=0, name="tool_validate_result"
    )
    def tool_validate_result(context: dict[str, Any]) -> None:
        """验证工具结果"""
        result = context.get("result")
        tool_name = context.get("tool_name", "unknown")

        if result is None:
            logger.warning(f"Tool {tool_name} returned None")
            return

        # 检查错误标识 - 只检查以 "Error:" 或 "Error " 开头的输出
        # 避免 "error" 字样出现在正常内容中导致的误报
        if isinstance(result, str) and result.strip():
            result_stripped = result.strip()
            if result_stripped.startswith(("Error:", "Error ")):
                logger.warning(f"Tool {tool_name} returned error: {result[:100]}")

    @registry.register(HookPoint.TOOL_CALL_AFTER, priority=1, name="tool_log_result")
    def tool_log_result(context: dict[str, Any]) -> None:
        """记录工具结果"""
        tool_name = context.get("tool_name", "unknown")
        result = context.get("result")
        duration_ms = context.get("duration_ms", 0)

        # 截断结果日志
        result_str = str(result)[:200] if result else "None"
        logger.debug(
            f"Tool result: {tool_name}, duration={duration_ms:.2f}ms, result={result_str}"
        )

    @registry.register(HookPoint.TOOL_CALL_ERROR, priority=0, name="tool_log_error")
    def tool_log_error(context: dict[str, Any]) -> None:
        """记录工具错误"""
        tool_name = context.get("tool_name", "unknown")
        error = context.get("error", "unknown error")
        tool_args = context.get("tool_args", {})

        logger.error(f"Tool error: {tool_name}, args={tool_args}, error={error}")

    @registry.register(
        HookPoint.TOOL_CALL_ERROR, priority=1, name="tool_record_failure"
    )
    def tool_record_failure(context: dict[str, Any]) -> None:
        """记录工具失败统计"""
        session = context.get("session")
        tool_name = context.get("tool_name", "unknown")
        error = context.get("error", "")

        if session and hasattr(session, "emit_event"):
            session.emit_event(
                "error_occurred",
                {
                    "error_type": "tool_execution",
                    "tool_name": tool_name,
                    "error_message": error[:500],
                },
            )


def register_subagent_hooks(registry: LifecycleHookRegistry) -> None:
    """注册子代理钩子"""

    @registry.register(HookPoint.SUBAGENT_SPAWN, priority=0, name="subagent_log_spawn")
    def subagent_log_spawn(context: dict[str, Any]) -> None:
        """记录子代理创建"""
        subagent_id = context.get("subagent_id", "unknown")
        subagent_type = context.get("subagent_type", "unknown")
        prompt_preview = str(context.get("prompt", ""))[:50]

        logger.info(
            f"Subagent spawned: id={subagent_id}, type={subagent_type}, "
            f"prompt={prompt_preview}..."
        )

    @registry.register(HookPoint.SUBAGENT_START, priority=0, name="subagent_log_start")
    def subagent_log_start(context: dict[str, Any]) -> None:
        """记录子代理开始"""
        subagent_id = context.get("subagent_id", "unknown")

        logger.debug(f"Subagent started: id={subagent_id}")

    @registry.register(HookPoint.SUBAGENT_END, priority=0, name="subagent_log_end")
    def subagent_log_end(context: dict[str, Any]) -> None:
        """记录子代理结束"""
        subagent_id = context.get("subagent_id", "unknown")
        result_preview = str(context.get("result", ""))[:100]
        duration_ms = context.get("duration_ms", 0)

        logger.info(
            f"Subagent ended: id={subagent_id}, "
            f"duration={duration_ms:.2f}ms, result={result_preview}..."
        )

    @registry.register(HookPoint.SUBAGENT_ERROR, priority=0, name="subagent_log_error")
    def subagent_log_error(context: dict[str, Any]) -> None:
        """记录子代理错误"""
        subagent_id = context.get("subagent_id", "unknown")
        error = context.get("error", "unknown error")

        logger.error(f"Subagent error: id={subagent_id}, error={error}")