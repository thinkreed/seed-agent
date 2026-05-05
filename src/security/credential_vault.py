"""
凭证保险库 - CredentialVault

基于 Harness Engineering "凭证永不进沙盒" 设计理念：
- 所有凭证存储在独立的加密保险库中
- Harness 和 Sandbox 无法直接访问
- 支持凭证轮换
- 支持审计日志
- 按作用域获取凭证（最小权限原则）

核心特性:
- Fernet 加密存储
- 作用域权限检查
- 凭证轮换历史
- 访问审计日志
- 持久化存储

参考来源: Harness Engineering "凭证永不进沙盒"
"""

import logging
from pathlib import Path

from src.security.vault import (
    AuditMixin,
    CredentialAccessLog,
    CredentialOpsMixin,
    CredentialRecord,
    CredentialRotationRecord,
    CredentialScope,
    CredentialType,
    EncryptionMixin,
    PersistenceMixin,
    _get_default_vault_path,
)

logger = logging.getLogger(__name__)


class CredentialVault(
    EncryptionMixin, PersistenceMixin, AuditMixin, CredentialOpsMixin
):
    """凭证保险库

    所有凭证存储在独立的加密存储中，Harness 和 Sandbox 无法直接访问。

    核心职责:
    1. 凭证加密存储 (Fernet)
    2. 作用域检查 (最小权限原则)
    3. 凭证轮换 (历史记录)
    4. 访问审计 (所有访问可追溯)
    5. 持久化存储 (JSON + 文件权限)

    安全特性:
    - 加密存储：所有凭证使用 Fernet 对称加密
    - 作用域限制：按请求作用域获取凭证
    - 访问审计：记录所有凭证访问
    - 轮换支持：支持凭证轮换并记录历史

    Example:
        vault = CredentialVault()

        # 存储凭证
        vault.store_credential("openai", "api_key", "sk-test123", scopes=["api_call"])

        # 获取凭证（按作用域）
        credential = vault.get_credential("openai", "api_key", scope="api_call")

        # 轮换凭证
        vault.rotate_credential("openai", "api_key", "sk-new456")

        # 查看审计日志
        audit_log = vault.get_access_audit_log()
    """

    # 凭证类型描述
    CREDENTIAL_TYPES = {
        CredentialType.API_KEY: "API 密钥",
        CredentialType.OAUTH_TOKEN: "OAuth 令牌",
        CredentialType.SSH_KEY: "SSH 密钥",
        CredentialType.DATABASE_PASSWORD: "数据库密码",
        CredentialType.CLOUD_CREDENTIALS: "云服务凭证",
    }

    # 作用域权限描述
    SCOPE_PERMISSIONS = {
        CredentialScope.API_CALL: "仅允许 API 调用",
        CredentialScope.FILE_UPLOAD: "允许文件上传",
        CredentialScope.ADMIN: "允许管理操作",
        CredentialScope.READONLY: "只读访问",
    }

    def __init__(
        self,
        vault_path: Path | None = None,
        encryption_key: str | None = None,
        auto_generate_key: bool = True,
    ):
        """初始化凭证保险库

        Args:
            vault_path: 保险库存储路径，默认 ~/.seed/vault
            encryption_key: 加密密钥（可选，自动生成）
            auto_generate_key: 是否自动生成加密密钥
        """
        self._vault_path = vault_path or _get_default_vault_path()
        self._credentials: dict[str, CredentialRecord] = {}
        self._access_logs: list[CredentialAccessLog] = []
        self._max_access_logs = 10000

        # 初始化加密密钥
        self._encryption_key: str | None = None
        if encryption_key:
            self._encryption_key = encryption_key
        elif auto_generate_key:
            self._encryption_key = self._init_encryption_key()

        # 初始化保险库
        self._init_vault()

        logger.info(
            f"CredentialVault initialized: "
            f"path={self._vault_path}, "
            f"credentials={len(self._credentials)}, "
            f"encryption_key_set={self._encryption_key is not None}"
        )

    def _init_vault(self) -> None:
        """初始化保险库

        创建目录结构，加载已有凭证和审计日志
        """
        # 创建保险库目录
        self._vault_path.mkdir(parents=True, exist_ok=True)

        # 加载已有凭证
        self._load_credentials()

        # 加载审计日志
        self._load_access_logs()

        logger.debug(f"Vault initialized with {len(self._credentials)} credentials")


# 导出公共接口（向后兼容）
__all__ = [
    "CredentialAccessLog",
    "CredentialRecord",
    "CredentialRotationRecord",
    "CredentialScope",
    "CredentialType",
    "CredentialVault",
]