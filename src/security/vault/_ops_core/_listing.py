"""
凭证列表和辅助模块

提供凭证的查询功能：
- list_credentials: 列出所有凭证（不含敏感值）
- has_credential: 检查凭证是否存在
- update_scopes: 更新凭证作用域

核心特性：
- 安全列出（不暴露凭证值）
- 快速存在检查
- 作用域动态更新
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from src.security.vault._types import CredentialAccessLog, CredentialRecord

logger = logging.getLogger(__name__)


class ListingMixin:
    """凭证列表和辅助功能 Mixin"""

    _credentials: dict[str, "CredentialRecord"]
    _vault_path: "Path"
    _access_logs: list["CredentialAccessLog"]

    if TYPE_CHECKING:
        def _persist_credentials(self) -> None: ...
        def _log_access(
            self, credential_id: str, scope: str, requester_id: str | None,
            action: str, success: bool, error: str | None = None,
        ) -> None: ...

    def list_credentials(self) -> list[dict[str, Any]]:
        """列出所有凭证（不暴露凭证值）"""
        result: list[dict[str, Any]] = []

        for cred_id, record in self._credentials.items():
            result.append({
                "credential_id": cred_id,
                "provider": record.provider,
                "type": record.type,
                "scopes": record.scopes,
                "created_at": record.created_at,
                "last_accessed": record.last_accessed,
                "access_count": record.access_count,
                "rotation_count": len(record.rotation_history),
                "last_rotated_at": record.rotated_at,
                "expiry": record.expiry,
                "metadata": record.metadata,
            })

        return result

    def has_credential(self, provider: str, credential_type: str) -> bool:
        """检查凭证是否存在"""
        credential_id = f"{provider}_{credential_type}"
        return credential_id in self._credentials

    def update_scopes(
        self,
        provider: str,
        credential_type: str,
        scopes: list[str],
        requester_id: str | None = None,
    ) -> None:
        """更新凭证作用域"""
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        self._credentials[credential_id].scopes = scopes
        self._persist_credentials()
        self._log_access(credential_id, "update", requester_id, "update_scopes", True)

        logger.info(f"Credential scopes updated: {credential_id}")