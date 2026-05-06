"""
凭证隔离沙盒 - 主类

基于 Harness Engineering "凭证永不进沙盒" 设计理念：
- Sandbox 内的代码无法访问凭证
- 禁止访问环境变量中的 API Key
- 进程级隔离执行（无凭证环境）
- 容器级隔离执行（不传递环境变量）

核心特性:
- 环境变量过滤（移除敏感环境变量）
- 进程级隔离（隔离环境执行）
- 容器级隔离（无凭证环境）
- 凭证代理集成（通过代理访问凭证）

重构说明：
- 环境处理移至 _environment.py
- 执行逻辑移至 _execution.py
- 代理管理移至 _proxy.py
- 输出过滤移至 _sanitize.py
- 类型定义移至 _types.py
- 状态管理移至 _state.py
- 验证逻辑移至 _verification.py
"""

import logging
import time
from pathlib import Path
from typing import Any

from src.sandbox import IsolationLevel
from src.security.credential_isolated._environment import (
    create_isolated_environment,
    detect_credential_access_attempt,
)
from src.security.credential_isolated._execution import execute_isolated
from src.security.credential_isolated._proxy import CredentialProxyManager
from src.security.credential_isolated._sanitize import sanitize_output
from src.security.credential_isolated._state import SandboxState
from src.security.credential_isolated._types import DEFAULT_BLOCKED_ENV_VARS
from src.security.credential_isolated._verification import verify_credential_isolation
from src.security.credential_proxy import CredentialProxy
from src.security.secure_sandbox import SecureExecutionResult, SecureSandbox
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


class CredentialIsolatedSandbox(SecureSandbox):
    """凭证隔离的 Sandbox

    Sandbox 内的代码无法访问凭证。
    """

    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        file_system_root: Path | None = None,
        workspace_path: Path | None = None,
        user_permission_level: str = "normal",
        enable_progressive_expansion: bool = True,
        enable_single_purpose_tools: bool = True,
        allow_risky_tools: bool = True,
        allow_dangerous_tools: bool = False,
        credential_proxy: CredentialProxy | None = None,
        blocked_env_vars: list[str] | None = None,
        enforce_credential_isolation: bool = True,
    ):
        super().__init__(
            isolation_level=isolation_level,
            file_system_root=file_system_root,
            workspace_path=workspace_path,
            user_permission_level=user_permission_level,
            enable_progressive_expansion=enable_progressive_expansion,
            enable_single_purpose_tools=enable_single_purpose_tools,
            allow_risky_tools=allow_risky_tools,
            allow_dangerous_tools=allow_dangerous_tools,
        )

        self._blocked_env_vars = blocked_env_vars or DEFAULT_BLOCKED_ENV_VARS.copy()
        self._enforce_credential_isolation = enforce_credential_isolation
        self._proxy_manager = CredentialProxyManager(credential_proxy)
        self._state = SandboxState(
            self._blocked_env_vars,
            enforce_credential_isolation,
            credential_proxy is not None,
        )

        logger.info(
            f"CredentialIsolatedSandbox initialized: "
            f"isolation={isolation_level.value}, blocked={len(self._blocked_env_vars)}"
        )

    async def execute_tools_isolated(
        self,
        tool_calls: list[dict],
        context: dict[str, Any] | None = None,
    ) -> list[SecureExecutionResult]:
        """凭证隔离的工具执行"""
        results: list[SecureExecutionResult] = []

        for tc in tool_calls:
            result = await self._execute_single_tool_isolated(tc, context)
            results.append(result)

        self._state.increment_executions(len(tool_calls))
        return results

    async def _execute_single_tool_isolated(
        self,
        tool_call: dict,
        context: dict[str, Any] | None = None,
    ) -> SecureExecutionResult:
        """执行单个工具（凭证隔离）"""
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
        classification = self._risk_classifier.classify(tool_name, tool_args)

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
                workspace_path=str(self._workspace_path),
                fs_root=str(self._fs_root),
                isolation_level=self.isolation_level,
                blocked_env_vars=self._blocked_env_vars,
                enforce_credential_isolation=self._enforce_credential_isolation,
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

    # === 凭证代理集成 ===

    async def get_credential_via_proxy(
        self,
        provider: str,
        credential_type: str,
        scope: str = "api_call",
        requester_id: str | None = None,
    ) -> str | None:
        """通过代理获取凭证"""
        return await self._proxy_manager.get_credential(
            provider, credential_type, scope, requester_id
        )

    async def execute_external_request_via_proxy(
        self,
        provider: str,
        credential_type: str,
        request_func: Any,
        request_context: dict[str, Any],
        requester_id: str | None = None,
    ) -> dict[str, Any]:
        """通过代理执行外部请求"""
        return await self._proxy_manager.execute_request(
            provider, credential_type, request_func, request_context, requester_id
        )

    # === 状态管理 ===

    def set_credential_proxy(self, proxy: CredentialProxy) -> None:
        """设置凭证代理"""
        self._proxy_manager.set_proxy(proxy)
        self._state.set_proxy_enabled(True)

    def add_blocked_env_var(self, var_name: str) -> None:
        """添加屏蔽的环境变量"""
        self._state.add_blocked_env_var(var_name)

    def remove_blocked_env_var(self, var_name: str) -> None:
        """移除屏蔽的环境变量"""
        self._state.remove_blocked_env_var(var_name)

    def get_blocked_env_vars(self) -> list[str]:
        """获取屏蔽的环境变量列表"""
        return self._state.get_blocked_env_vars()

    def get_isolation_stats(self) -> dict[str, Any]:
        """获取隔离统计信息"""
        return self._state.get_isolation_stats(self.get_secure_execution_stats())

    def get_status_isolated(self) -> dict[str, Any]:
        """获取凭证隔离沙盒完整状态"""
        return self._state.get_status(self.get_status_secure())

    # === 验证 ===

    async def verify_credential_isolation(self) -> dict[str, Any]:
        """验证凭证隔离是否有效"""
        return await verify_credential_isolation(self._blocked_env_vars)

    # === 向后兼容别名 ===

    def _create_isolated_environment(self) -> dict[str, str]:
        """向后兼容别名"""
        return create_isolated_environment(self._blocked_env_vars)

    def _detect_credential_access_attempt(self, content: str) -> bool:
        """向后兼容别名"""
        return detect_credential_access_attempt(
            content, enforce=self._enforce_credential_isolation
        )

    def _sanitize_output(self, output: str) -> str:
        """向后兼容别名"""
        return sanitize_output(output)