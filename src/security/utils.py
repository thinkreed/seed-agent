"""
安全工具函数 - Security Utilities

提供环境变量清理等安全辅助功能。

核心功能:
- get_safe_environment: 返回清理后的环境变量（移除敏感凭证）

使用:
- SinglePurposeToolFactory: 执行子进程时清理环境
- CredentialIsolatedSandbox: 创建隔离执行环境

参考来源: Harness Engineering "凭证永不进沙盒"
"""

import logging
import os

from src.security.constants import SENSITIVE_ENV_VARS, ENV_VAR_BLOCK_PATTERNS

logger = logging.getLogger(__name__)


def get_safe_environment() -> dict[str, str]:
    """获取安全的环境变量字典（移除敏感凭证）

    移除所有敏感环境变量，确保凭证不暴露给子进程。

    Returns:
        清理后的环境变量，不含 API Key、Token、密码等
    """
    safe_env = os.environ.copy()

    # 移除敏感环境变量
    for var in SENSITIVE_ENV_VARS:
        if var in safe_env:
            del safe_env[var]

    # 模式匹配移除（如 *_KEY, *_TOKEN, *_SECRET）
    for key in list(safe_env.keys()):
        for pattern in ENV_VAR_BLOCK_PATTERNS:
            if key.endswith(pattern) or pattern in key:
                del safe_env[key]
                break

    return safe_env


# 公共导出
__all__ = ["get_safe_environment"]