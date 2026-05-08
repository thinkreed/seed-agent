"""
凭证隔离沙盒 - 主类

基于 Harness Engineering "凭证永不进沙盒" 设计理念。
核心特性：环境变量过滤、进程/容器级隔离、凭证代理集成。

拆分模块: _environment, _execution, _tool_execution, _state_api,
_proxy, _sanitize, _types, _state, _verification, _compat
"""

import logging
from typing import Any

from src.sandbox import IsolationLevel
from src.security.credential_isolated._compat import CompatAPI
from src.security.credential_isolated._proxy import CredentialProxyManager
from src.security.credential_isolated._state import SandboxState
from src.security.credential_isolated._state_api import StateAPI
from src.security.credential_isolated._tool_execution import execute_tools_isolated
from src.security.credential_isolated._types import DEFAULT_BLOCKED_ENV_VARS
from src.security.credential_isolated._verification import verify_credential_isolation
from src.security.credential_proxy import CredentialProxy
from src.security.secure_sandbox import SecureExecutionResult, SecureSandbox

logger = logging.getLogger(__name__)


class CredentialIsolatedSandbox(SecureSandbox):
    """凭证隔离的 Sandbox：代码无法访问凭证"""

    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        file_system_root: Any = None,
        workspace_path: Any = None,
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
        self._state_api = StateAPI(self)
        self._compat_api = CompatAPI(
            self._blocked_env_vars, enforce_credential_isolation
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
        return await execute_tools_isolated(tool_calls, context, self)

    # === 凭证代理集成 ===

    async def get_credential_via_proxy(
        self, provider: str, credential_type: str, scope: str = "api_call",
        requester_id: str | None = None,
    ) -> str | None:
        """通过代理获取凭证"""
        return await self._proxy_manager.get_credential(
            provider, credential_type, scope, requester_id
        )

    async def execute_external_request_via_proxy(
        self, provider: str, credential_type: str, request_func: Any,
        request_context: dict[str, Any], requester_id: str | None = None,
    ) -> dict[str, Any]:
        """通过代理执行外部请求"""
        return await self._proxy_manager.execute_request(
            provider, credential_type, request_func, request_context, requester_id
        )

    # === 状态管理 API ===

    def set_credential_proxy(self, proxy: CredentialProxy) -> None:
        """设置凭证代理"""
        self._state_api.set_credential_proxy(proxy)

    def add_blocked_env_var(self, var_name: str) -> None:
        """添加屏蔽的环境变量"""
        self._state_api.add_blocked_env_var(var_name)

    def remove_blocked_env_var(self, var_name: str) -> None:
        """移除屏蔽的环境变量"""
        self._state_api.remove_blocked_env_var(var_name)

    def get_blocked_env_vars(self) -> list[str]:
        """获取屏蔽的环境变量列表"""
        return self._state_api.get_blocked_env_vars()

    def get_isolation_stats(self) -> dict[str, Any]:
        """获取隔离统计信息"""
        return self._state_api.get_isolation_stats()

    def get_status_isolated(self) -> dict[str, Any]:
        """获取凭证隔离沙盒完整状态"""
        return self._state_api.get_status_isolated()

    # === 验证 ===

    async def verify_credential_isolation(self) -> dict[str, Any]:
        """验证凭证隔离是否有效"""
        return await verify_credential_isolation(self._blocked_env_vars)

    # === 向后兼容别名 ===

    def _create_isolated_environment(self) -> dict[str, str]:
        """向后兼容别名"""
        return self._compat_api.create_isolated_environment()

    def _detect_credential_access_attempt(self, content: str) -> bool:
        """向后兼容别名"""
        return self._compat_api.detect_credential_access_attempt(content)

    def _sanitize_output(self, output: str) -> str:
        """向后兼容别名"""
        return self._compat_api.sanitize_output(output)