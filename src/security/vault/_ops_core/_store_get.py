"""
凭证存储和获取模块

提供凭证的基本操作：
- store_credential: 存储凭证
- get_credential: 获取凭证

核心特性：
- 加密存储
- 过期检查
- 作用域权限检查
"""

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from src.security.vault._types import CredentialAccessLog, CredentialRecord

logger = logging.getLogger(__name__)


class StoreGetMixin:
    """凭证存储和获取功能 Mixin"""

    _credentials: dict[str, "CredentialRecord"]
    _vault_path: "Path"
    _access_logs: list["CredentialAccessLog"]

    if TYPE_CHECKING:
        def _encrypt(self, value: str) -> str: ...
        def _decrypt(self, value: str) -> str: ...
        def _persist_credentials(self) -> None: ...
        def _log_access(
            self, credential_id: str, scope: str, requester_id: str | None,
            action: str, success: bool, error: str | None = None,
        ) -> None: ...

    def store_credential(
        self,
        provider: str,
        credential_type: str,
        credential_value: str,
        scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        expiry: float | None = None,
    ) -> str:
        """存储凭证"""
        from src.security.vault._types import CredentialRecord, CredentialScope

        if not credential_value:
            raise ValueError("Credential value cannot be empty")

        credential_id = f"{provider}_{credential_type}"
        encrypted_value = self._encrypt(credential_value)

        record = CredentialRecord(
            provider=provider,
            type=credential_type,
            value_encrypted=encrypted_value,
            scopes=scopes or [CredentialScope.API_CALL.value],
            metadata=metadata or {},
            created_at=time.time(),
            last_accessed=None,
            access_count=0,
            rotation_history=[],
            expiry=expiry,
        )

        self._credentials[credential_id] = record
        self._persist_credentials()
        self._log_access(credential_id, "store", None, "store_credential", True)

        logger.info(f"Credential stored: {credential_id}, scopes={record.scopes}")
        return credential_id

    def get_credential(
        self,
        provider: str,
        credential_type: str,
        scope: str = "api_call",
        requester_id: str | None = None,
    ) -> str:
        """获取凭证"""
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        record = self._credentials[credential_id]

        # 过期检查
        if record.expiry and time.time() > record.expiry:
            self._log_access(credential_id, scope, requester_id, "get_credential", False, "Expired")
            raise RuntimeError(f"Credential expired: {credential_id}")

        # 作用域检查
        if scope not in record.scopes:
            error_msg = f"Scope '{scope}' not allowed for {credential_id}. Allowed scopes: {record.scopes}"
            self._log_access(credential_id, scope, requester_id, "get_credential", False, error_msg)
            raise PermissionError(error_msg)

        decrypted_value = self._decrypt(record.value_encrypted)
        record.last_accessed = time.time()
        record.access_count += 1
        self._log_access(credential_id, scope, requester_id, "get_credential", True)

        logger.debug(f"Credential accessed: {credential_id}, scope={scope}")
        return decrypted_value