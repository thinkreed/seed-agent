"""
凭证隔离沙盒 - Package 入口

导出:
- CredentialIsolatedSandbox: 主类
- 辅助函数（可选）
"""

from src.security.credential_isolated._sandbox import CredentialIsolatedSandbox
from src.security.credential_isolated._types import (
    CREDENTIAL_ACCESS_PATTERNS,
    DEFAULT_BLOCKED_ENV_VARS,
)

__all__ = [
    "CredentialIsolatedSandbox",
    "CREDENTIAL_ACCESS_PATTERNS",
    "DEFAULT_BLOCKED_ENV_VARS",
]