"""
安全沙盒执行模块

包含安全执行核心逻辑
"""

import logging
import time
from typing import Any

from src.security._secure_sandbox_types import SecureExecutionResult
from src.security.risk_classifier import RiskAction
from src.security.tool_expander import ToolTier
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


async def execute_single_tool_secure(
    tool_call: dict,
    context: dict[str, Any] | None,
    risk_classifier: Any,
    tool_expander: Any,
    tool_factory: Any,
    tools: Any,
    user_confirmation_callback: Any,
    user_permission_level: str,
    record_execution_func: Any,
) -> SecureExecutionResult:
    """执行单个工具（带安全检查）

    流程:
    1. 工具可用性检查（渐进式扩展）
    2. 风险分类
    3. 根据风险等级处理（block/request_confirm/log_and_execute/auto_execute）
    4. 执行工具
    5. 记录结果

    Args:
        tool_call: 工具调用字典
        context: 执行上下文
        risk_classifier: 风险分类器实例
        tool_expander: 工具扩展器实例
        tool_factory: 单用途工具工厂实例
        tools: 工具注册表实例
        user_confirmation_callback: 用户确认回调
        user_permission_level: 用户权限等级
        record_execution_func: 记录执行的回调函数

    Returns:
        SecureExecutionResult: 安全执行结果
    """
    tool_call_id = tool_call.get("id", "unknown")
    func_data = tool_call.get("function", {})
    tool_name = func_data.get("name", "unknown")
    raw_args = func_data.get("arguments", "{}")

    start_time = time.time()

    # 使用统一函数解析参数
    tool_args = parse_tool_arguments(raw_args)
    if is_parse_failed(tool_args):
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content="Error: Failed to parse arguments: invalid JSON",
            success=False,
            duration_ms=0.0,
        )

    # 1. 工具可用性检查（渐进式扩展）
    if tool_expander and context:
        available_tools = tool_expander.get_available_tools(context)
        if tool_name not in available_tools:
            current_tier = tool_expander.get_current_tier()
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"[BLOCKED] Tool '{tool_name}' not available in current tier ({current_tier.value})",
                success=False,
                blocked=True,
                duration_ms=(time.time() - start_time) * 1000,
            )

    # 2. 风险分类
    classification = risk_classifier.classify(tool_name, tool_args)

    # 3. 根据风险等级处理
    if classification.action == RiskAction.BLOCK:
        # 直接拦截
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=f"[BLOCKED] Tool '{tool_name}' blocked by security policy (risk: {classification.risk_level.value}, score: {classification.score:.2f})",
            success=False,
            risk_level=classification.risk_level,
            action_taken=classification.action,
            blocked=True,
            duration_ms=(time.time() - start_time) * 1000,
        )

    if classification.action == RiskAction.REQUEST_CONFIRM:
        # 请求用户确认
        confirmed = await _request_user_approval(
            tool_name,
            classification.risk_level,
            tool_args,
            user_confirmation_callback,
            user_permission_level,
        )

        if not confirmed:
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"[CANCELLED] User cancelled '{tool_name}' (risk: {classification.risk_level.value})",
                success=False,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                user_confirmed=False,
                duration_ms=(time.time() - start_time) * 1000,
            )

    # 4. 日志记录（caution 级别）
    if classification.action == RiskAction.LOG_AND_EXECUTE:
        logger.warning(
            f"Executing cautious tool: {tool_name} "
            f"(risk: {classification.risk_level.value}, "
            f"score: {classification.score:.2f}, "
            f"factors: {classification.factors})"
        )

    # 5. 执行工具
    try:
        # 优先使用单用途工具
        if tool_factory and _is_single_purpose_tool(tool_factory, tool_name):
            result_content = _execute_single_purpose_tool(tool_factory, tool_name, tool_args)
        else:
            # 使用标准工具执行
            result_content = await _execute_standard_tool(tools, tool_name, tool_args)

        duration_ms = (time.time() - start_time) * 1000

        # 记录成功结果
        execution_result = SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=result_content,
            success=True,
            risk_level=classification.risk_level,
            action_taken=classification.action,
            duration_ms=duration_ms,
            user_confirmed=True
            if classification.action == RiskAction.REQUEST_CONFIRM
            else None,
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Error: {type(e).__name__}: {str(e)[:200]}"

        execution_result = SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=error_msg,
            success=False,
            risk_level=classification.risk_level,
            action_taken=classification.action,
            duration_ms=duration_ms,
        )

    # 6. 记录执行历史
    if record_execution_func:
        record_execution_func(execution_result)

    return execution_result


async def _request_user_approval(
    tool_name: str,
    risk_level: Any,
    args: dict[str, Any],
    user_confirmation_callback: Any,
    user_permission_level: str,
) -> bool:
    """请求用户批准

    Args:
        tool_name: 工具名称
        risk_level: 风险等级
        args: 工具参数
        user_confirmation_callback: 用户确认回调
        user_permission_level: 用户权限等级

    Returns:
        是否批准
    """
    if user_confirmation_callback:
        return user_confirmation_callback(tool_name, risk_level.value, args)

    # 默认行为：记录并返回 False（需要外部确认机制）
    logger.warning(
        f"Tool '{tool_name}' requires user confirmation (risk: {risk_level.value}) "
        f"but no callback configured - defaulting to deny"
    )
    return False


def _is_single_purpose_tool(tool_factory: Any, tool_name: str) -> bool:
    """检查是否为单用途工具"""
    if tool_factory is None:
        return False

    return tool_factory.get_tool_config(tool_name) is not None


def _execute_single_purpose_tool(
    tool_factory: Any,
    tool_name: str,
    args: dict[str, Any],
) -> str:
    """执行单用途工具"""
    if tool_factory is None:
        return "[ERROR] Single-purpose tool factory not enabled"

    try:
        tool_func = tool_factory.create_tool(tool_name)
        return tool_func(**args)
    except ValueError as e:
        return f"[ERROR] {e}"
    except Exception as e:
        return f"[ERROR] Tool execution failed: {type(e).__name__}: {str(e)[:200]}"


async def _execute_standard_tool(
    tools: Any,
    tool_name: str,
    args: dict[str, Any],
) -> str:
    """执行标准工具（通过 ToolRegistry）"""
    if not tools:
        raise RuntimeError("Sandbox has no tools registered")

    result = await tools.execute(tool_name, **args)
    return str(result)