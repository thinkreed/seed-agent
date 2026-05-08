"""
凭证隔离沙盒 - 工具执行

处理工具的凭证隔离执行逻辑。
"""

import time
import logging
from typing import Any

from src.security.credential_isolated._execution import execute_isolated
from src.security.secure_sandbox import SecureExecutionResult
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


async def execute_tools_isolated(
    tool_calls: list[dict],
    context: dict[str, Any] | None,
    sandbox_instance: Any,
) -> list[SecureExecutionResult]:
    """凭证隔离的工具执行

    Args:
        tool_calls: 工具调用列表
        context: 执行上下文
        sandbox_instance: CredentialIsolatedSandbox 实例

    Returns:
        执行结果列表
    """
    results: list[SecureExecutionResult] = []

    for tc in tool_calls:
        result = await _execute_single_tool_isolated(tc, context, sandbox_instance)
        results.append(result)

    sandbox_instance._state.increment_executions(len(tool_calls))
    return results


async def _execute_single_tool_isolated(
    tool_call: dict,
    context: dict[str, Any] | None,
    sandbox_instance: Any,
) -> SecureExecutionResult:
    """执行单个工具（凭证隔离）

    Args:
        tool_call: 工具调用
        context: 执行上下文
        sandbox_instance: CredentialIsolatedSandbox 实例

    Returns:
        执行结果
    """
    tool_call_id = tool_call.get("id", "unknown")
    func_data = tool_call.get("function", {})
    tool_name = func_data.get("name", "unknown")
    raw_args = func_data.get("arguments", "{}")

    tool_args = parse_tool_arguments(raw_args)
    if is_parse_failed(tool_args):
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content="Error: Failed to parse arguments",
            success=False,
            duration_ms=0.0,
        )

    start_time = time.time()
    classification = sandbox_instance._risk_classifier.classify(tool_name, tool_args)

    if classification.action == "block":
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=f"[BLOCKED] Tool '{tool_name}' blocked",
            success=False,
            risk_level=classification.risk_level,
            blocked=True,
            duration_ms=(time.time() - start_time) * 1000,
        )

    try:
        result_content = await execute_isolated(
            tool_name=tool_name,
            args=tool_args,
            workspace_path=str(sandbox_instance._workspace_path),
            fs_root=str(sandbox_instance._fs_root),
            isolation_level=sandbox_instance.isolation_level,
            blocked_env_vars=sandbox_instance._blocked_env_vars,
            enforce_credential_isolation=sandbox_instance._enforce_credential_isolation,
            timeout=30.0,
        )

        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=result_content,
            success=True,
            risk_level=classification.risk_level,
            duration_ms=(time.time() - start_time) * 1000,
        )

    except Exception as e:
        return SecureExecutionResult(
            tool_call_id=tool_call_id,
            content=f"Error: {type(e).__name__}: {str(e)[:200]}",
            success=False,
            risk_level=classification.risk_level,
            duration_ms=(time.time() - start_time) * 1000,
        )