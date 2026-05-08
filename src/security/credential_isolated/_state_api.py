"""
凭证隔离沙盒 - 状态管理 API

提供沙盒状态管理的公共 API 方法。
"""

from typing import Any

from src.security.credential_proxy import CredentialProxy


class StateAPI:
    """状态管理 API 提供者"""

    def __init__(self, sandbox_instance: Any):
        """初始化状态 API

        Args:
            sandbox_instance: CredentialIsolatedSandbox 实例
        """
        self._sandbox = sandbox_instance

    def set_credential_proxy(self, proxy: CredentialProxy) -> None:
        """设置凭证代理"""
        self._sandbox._proxy_manager.set_proxy(proxy)
        self._sandbox._state.set_proxy_enabled(True)

    def add_blocked_env_var(self, var_name: str) -> None:
        """添加屏蔽的环境变量"""
        self._sandbox._state.add_blocked_env_var(var_name)

    def remove_blocked_env_var(self, var_name: str) -> None:
        """移除屏蔽的环境变量"""
        self._sandbox._state.remove_blocked_env_var(var_name)

    def get_blocked_env_vars(self) -> list[str]:
        """获取屏蔽的环境变量列表"""
        return self._sandbox._state.get_blocked_env_vars()

    def get_isolation_stats(self) -> dict[str, Any]:
        """获取隔离统计信息"""
        return self._sandbox._state.get_isolation_stats(
            self._sandbox.get_secure_execution_stats()
        )

    def get_status_isolated(self) -> dict[str, Any]:
        """获取凭证隔离沙盒完整状态"""
        return self._sandbox._state.get_status(self._sandbox.get_status_secure())