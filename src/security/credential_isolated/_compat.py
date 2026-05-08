"""
凭证隔离沙盒 - 向后兼容别名

提供向后兼容的内部方法别名。
"""

from src.security.credential_isolated._environment import (
    create_isolated_environment,
    detect_credential_access_attempt,
)
from src.security.credential_isolated._sanitize import sanitize_output


class CompatAPI:
    """向后兼容 API 提供者"""

    def __init__(self, blocked_env_vars: list[str], enforce_credential_isolation: bool):
        self._blocked_env_vars = blocked_env_vars
        self._enforce_credential_isolation = enforce_credential_isolation

    def create_isolated_environment(self) -> dict[str, str]:
        """创建隔离环境（向后兼容）"""
        return create_isolated_environment(self._blocked_env_vars)

    def detect_credential_access_attempt(self, content: str) -> bool:
        """检测凭证访问尝试（向后兼容）"""
        return detect_credential_access_attempt(
            content, enforce=self._enforce_credential_isolation
        )

    def sanitize_output(self, output: str) -> str:
        """过滤输出（向后兼容）"""
        return sanitize_output(output)