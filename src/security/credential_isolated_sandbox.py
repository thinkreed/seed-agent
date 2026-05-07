"""
凭证隔离沙盒 - 兼容性入口

原 credential_isolated_sandbox.py 已重构为 credential_isolated/ package。
此文件保持向后兼容，从 package 导入主类。

模块拆分:
- _types.py: 类型定义和常量
- _environment.py: 环境隔离
- _sanitize.py: 输出清洗
- _execution.py: 隔离执行
- _proxy.py: 凭证代理集成
- _sandbox.py: 主类

参考来源: Harness Engineering "凭证永不进沙盒"
"""

# 从 package 导入，保持向后兼容
from src.security.credential_isolated import (
    CREDENTIAL_ACCESS_PATTERNS,
    DEFAULT_BLOCKED_ENV_VARS,
    CredentialIsolatedSandbox,
)

__all__ = [
    "CREDENTIAL_ACCESS_PATTERNS",
    "DEFAULT_BLOCKED_ENV_VARS",
    "CredentialIsolatedSandbox",
]