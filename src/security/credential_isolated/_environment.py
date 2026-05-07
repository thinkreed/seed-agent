"""
凭证隔离沙盒 - 环境隔离模块

负责:
- 创建无凭证环境变量字典
- 环境变量过滤和屏蔽
"""

import logging
import os

from src.security.credential_isolated._types import (
    DEFAULT_BLOCKED_ENV_VARS,
    DEFAULT_ENV_VAR_BLOCK_PATTERNS,
)

logger = logging.getLogger(__name__)


def create_isolated_environment(
    blocked_env_vars: list[str] | None = None,
    block_patterns: list[str] | None = None,
) -> dict[str, str]:
    """创建隔离的环境变量字典

    移除所有敏感环境变量，确保凭证不暴露。

    Args:
        blocked_env_vars: 自定义屏蔽环境变量列表
        block_patterns: 自定义屏蔽模式列表

    Returns:
        无凭证的环境变量字典
    """
    isolated_env = os.environ.copy()
    vars_to_block = blocked_env_vars or DEFAULT_BLOCKED_ENV_VARS
    patterns_to_block = block_patterns or DEFAULT_ENV_VAR_BLOCK_PATTERNS

    # 移除敏感环境变量
    for var in vars_to_block:
        if var in isolated_env:
            logger.debug(f"Blocked environment variable: {var}")
            del isolated_env[var]

    # 模式匹配移除（如 *_KEY, *_TOKEN, *_SECRET）
    for key in list(isolated_env.keys()):
        for pattern in patterns_to_block:
            if key.endswith(pattern) or pattern in key:
                logger.debug(f"Blocked environment variable (pattern): {key}")
                del isolated_env[key]
                break

    return isolated_env


def detect_credential_access_attempt(
    content: str,
    patterns: list[str] | None = None,
    enforce: bool = True,
) -> bool:
    """检测凭证访问尝试

    检查代码或参数是否包含访问凭证的意图。

    Args:
        content: 要检查的内容
        patterns: 检测模式列表
        enforce: 是否启用检测

    Returns:
        是否存在凭证访问尝试
    """
    if not enforce:
        return False

    check_patterns = patterns or [
        "os.environ",
        "getenv",
        "environ.get",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "BAILIAN_API_KEY",
        "AWS_ACCESS_KEY",
        "GITHUB_TOKEN",
        "api_key",
        "apiKey",
        "API_KEY",
    ]

    return any(pattern.lower() in content.lower() for pattern in check_patterns)