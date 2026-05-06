"""
凭证隔离沙盒 - 状态管理

处理沙盒的状态获取和配置管理。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SandboxState:
    """沙盒状态管理器"""

    def __init__(
        self,
        blocked_env_vars: list[str],
        enforce_credential_isolation: bool,
        proxy_enabled: bool,
    ):
        self._blocked_env_vars = blocked_env_vars
        self._enforce_credential_isolation = enforce_credential_isolation
        self._proxy_enabled = proxy_enabled
        self._isolated_executions_count = 0
        self._credential_access_attempts = 0

    def add_blocked_env_var(self, var_name: str) -> None:
        """添加屏蔽的环境变量"""
        if var_name not in self._blocked_env_vars:
            self._blocked_env_vars.append(var_name)
            logger.info(f"Added blocked environment variable: {var_name}")

    def remove_blocked_env_var(self, var_name: str) -> None:
        """移除屏蔽的环境变量"""
        if var_name in self._blocked_env_vars:
            self._blocked_env_vars.remove(var_name)
            logger.info(f"Removed blocked environment variable: {var_name}")

    def get_blocked_env_vars(self) -> list[str]:
        """获取屏蔽的环境变量列表"""
        return self._blocked_env_vars.copy()

    def increment_executions(self, count: int = 1) -> None:
        """增加执行计数"""
        self._isolated_executions_count += count

    def increment_credential_attempts(self) -> None:
        """增加凭证访问尝试计数"""
        self._credential_access_attempts += 1

    def set_proxy_enabled(self, enabled: bool) -> None:
        """设置代理启用状态"""
        self._proxy_enabled = enabled

    def get_isolation_stats(self, base_stats: dict[str, Any]) -> dict[str, Any]:
        """获取隔离统计信息"""
        return {
            **base_stats,
            "credential_isolation": {
                "enforced": self._enforce_credential_isolation,
                "blocked_env_vars_count": len(self._blocked_env_vars),
                "isolated_executions_count": self._isolated_executions_count,
                "credential_access_attempts_blocked": self._credential_access_attempts,
                "credential_proxy_enabled": self._proxy_enabled,
            },
        }

    def get_status(self, base_status: dict[str, Any]) -> dict[str, Any]:
        """获取完整状态"""
        return {
            **base_status,
            "credential_isolation": {
                "enforced": self._enforce_credential_isolation,
                "blocked_env_vars": len(self._blocked_env_vars),
                "isolated_executions": self._isolated_executions_count,
                "credential_attempts_blocked": self._credential_access_attempts,
            },
        }