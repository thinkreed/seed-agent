"""
凭证轮换和删除模块

提供凭证的生命周期管理：
- rotate_credential: 轮换凭证
- delete_credential: 删除凭证
- clear_expired_credentials: 清理过期凭证

核心特性：
- 轮换历史记录
- 安全删除
- 自动清理
"""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from src.security.vault._types import CredentialAccessLog, CredentialRecord

logger = logging.getLogger(__name__)


class RotationMixin:
    """凭证轮换和删除功能 Mixin"""

    _credentials: dict[str, "CredentialRecord"]
    _vault_path: "Path"
    _access_logs: list["CredentialAccessLog"]

    if TYPE_CHECKING:
        def _encrypt(self, value: str) -> str: ...
        def _persist_credentials(self) -> None: ...
        def _log_access(
            self, credential_id: str, scope: str, requester_id: str | None,
            action: str, success: bool, error: str | None = None,
        ) -> None: ...

    def rotate_credential(
        self,
        provider: str,
        credential_type: str,
        new_value: str,
        rotated_by: str = "system",
        reason: str | None = None,
    ) -> None:
        """轮换凭证"""
        from src.security.vault._types import CredentialRotationRecord

        if not new_value:
            raise ValueError("New credential value cannot be empty")

        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        record = self._credentials[credential_id]

        rotation_record = CredentialRotationRecord(
            old_value_encrypted=record.value_encrypted,
            rotated_at=time.time(),
            rotated_by=rotated_by,
            reason=reason,
        )
        record.rotation_history.append({
            "old_value_encrypted": rotation_record.old_value_encrypted,
            "rotated_at": rotation_record.rotated_at,
            "rotated_by": rotation_record.rotated_by,
            "reason": rotation_record.reason,
        })

        record.value_encrypted = self._encrypt(new_value)
        record.rotated_at = time.time()
        self._persist_credentials()
        self._log_access(credential_id, "rotate", rotated_by, "rotate_credential", True)

        logger.info(f"Credential rotated: {credential_id}, by={rotated_by}")

    def delete_credential(
        self, provider: str, credential_type: str, requester_id: str | None = None
    ) -> bool:
        """删除凭证"""
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        del self._credentials[credential_id]
        self._persist_credentials()
        self._log_access(credential_id, "delete", requester_id, "delete_credential", True)

        logger.info(f"Credential deleted: {credential_id}")
        return True

    def clear_expired_credentials(self) -> int:
        """清理过期凭证"""
        expired_ids = [
            cred_id
            for cred_id, record in self._credentials.items()
            if record.expiry and time.time() > record.expiry
        ]

        for cred_id in expired_ids:
            del self._credentials[cred_id]
            self._log_access(cred_id, "cleanup", "system", "clear_expired", True)

        if expired_ids:
            self._persist_credentials()
            logger.info(f"Cleaned up {len(expired_ids)} expired credentials")

        return len(expired_ids)