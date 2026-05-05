"""
单用途工具类型定义

包含共享的类型、常量和辅助函数
"""

from collections.abc import Callable

# 实现函数类型
ToolImplFunc = Callable[[dict], str]

# 延迟导入辅助函数
def _get_sensitive_env_vars() -> list[str]:
    """延迟获取敏感环境变量列表"""
    from src.security.constants import SENSITIVE_ENV_VARS

    return SENSITIVE_ENV_VARS


def _get_safe_env() -> dict[str, str]:
    """延迟获取安全环境"""
    from src.security.utils import get_safe_environment

    return get_safe_environment()