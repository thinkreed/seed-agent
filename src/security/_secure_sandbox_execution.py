"""
安全沙盒执行模块

包含安全执行核心逻辑
"""

import logging
import time
from typing import Any

from src.security._secure_sandbox_types import SecureExecutionResult
from src.security._secure_sandbox_utils import (
    execute_single_purpose_tool,
    execute_standard_tool,
    is_single_purpose_tool,
    request_user_approval,
)
from src.security.risk_classifier import RiskAction
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
    """执行单个工具（带安全检查）"""
    tool_call_id = tool_call.get("id", "unknown")
    func_data = tool_call.get("function", {})
    tool_name = func_data.get("name", "unknown")
    raw_args = func_data.get("arguments", "{}")

    start_time = time.time()

    tool_args = parse_tool_arguments(raw_args)
    if is_parse_failed(tool_args):
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content="Error: Failed to parse arguments: invalid JSON",
            success=False,
            duration_ms=0.0,
        )

    # 1. 工具可用性检查
    if tool_expander and context:
        available_tools = tool_expander.get_available_tools(context)
        if tool_name not in available_tools:
            current_tier = tool_expander.get_current_tier()
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"[BLOCKED] Tool '{tool_name}' not available in tier ({current_tier.value})",
                success=False,
                blocked=True,
                duration_ms=(time.time() - start_time) * 1000,
            )

    # 2. 风险分类
    classification = risk_classifier.classify(tool_name, tool_args)

    # 3. 根据风险等级处理
    if classification.action == RiskAction.BLOCK:
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=f"[BLOCKED] Tool '{tool_name}' blocked (risk: {classification.risk_level.value})",
            success=False,
            risk_level=classification.risk_level,
            action_taken=classification.action,
            blocked=True,
            duration_ms=(time.time() - start_time) * 1000,
        )

    if classification.action == RiskAction.REQUEST_CONFIRM:
        confirmed = await request_user_approval(
            tool_name, classification.risk_level, tool_args,
            user_confirmation_callback, user_permission_level
        )
        if not confirmed:
            return SecureExecutionResult(
                tool_call_id=tool_call_id,
                content=f"[CANCELLED] User cancelled '{tool_name}'",
                success=False,
                risk_level=classification.risk_level,
                action_taken=classification.action,
                user_confirmed=False,
                duration_ms=(time.time() - start_time) * 1000,
            )

    # 4. 日志记录
    if classification.action == RiskAction.LOG_AND_EXECUTE:
        logger.warning(f"Executing cautious tool: {tool_name} (risk: {classification.risk_level.value})")

    # 5. 执行工具
    try:
        if tool_factory and is_single_purpose_tool(tool_factory, tool_name):
            result_content = execute_single_purpose_tool(tool_factory, tool_name, tool_args)
        else:
            result_content = await execute_standard_tool(tools, tool_name, tool_args)

        duration_ms = (time.time() - start_time) * 1000
        execution_result = SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=result_content,
            success=True,
            risk_level=classification.risk_level,
            action_taken=classification.action,
            duration_ms=duration_ms,
            user_confirmed=True if classification.action == RiskAction.REQUEST_CONFIRM else None,
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