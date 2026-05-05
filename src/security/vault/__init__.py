"""
凭证保险库子模块

提供凭证类型、加密、持久化和审计功能的模块化实现。

公共接口：
- CredentialType: 凭证类型枚举
- CredentialScope: 凭证作用域枚举
- CredentialAccessLog: 凭证访问日志数据类
- CredentialRotationRecord: 凭证轮换记录数据类
- CredentialRecord: 凭证记录数据类
- EncryptionMixin: 加密功能 Mixin
- PersistenceMixin: 持久化功能 Mixin
- AuditMixin: 审计功能 Mixin
- CredentialOpsMixin: 凭证操作功能 Mixin
- _get_default_vault_path: 获取默认保险库路径
"""

from src.security.vault._types import (
    CredentialAccessLog,
    CredentialRecord,
    CredentialRotationRecord,
    CredentialScope,
    CredentialType,
    _get_default_vault_path,
)
from src.security.vault._encryption import EncryptionMixin
from src.security.vault._persistence import PersistenceMixin
from src.security.vault._audit import AuditMixin
from src.security.vault._credential_ops import CredentialOpsMixin

__all__ = [
    # 类型定义
    "CredentialType",
    "CredentialScope",
    "CredentialAccessLog",
    "CredentialRotationRecord",
    "CredentialRecord",
    # Mixin 类
    "EncryptionMixin",
    "PersistenceMixin",
    "AuditMixin",
    "CredentialOpsMixin",
    # 辅助函数
    "_get_default_vault_path",
]