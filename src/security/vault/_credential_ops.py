"""
凭证保险库凭证操作模块

包含凭证的存储、获取、轮换、删除等操作功能。

模块拆分:
- _ops_core/_store_get.py: 存储和获取
- _ops_core/_rotation.py: 轮换和删除
- _ops_core/_listing.py: 列表和辅助
"""

import logging
from typing import TYPE_CHECKING

from src.security.vault._ops_core import (
    ListingMixin,
    RotationMixin,
    StoreGetMixin,
)

if TYPE_CHECKING:
    from pathlib import Path

    from src.security.vault._types import CredentialAccessLog, CredentialRecord

logger = logging.getLogger(__name__)


class CredentialOpsMixin(StoreGetMixin, RotationMixin, ListingMixin):
    """凭证操作功能 Mixin 类

    使用 Mixin 组合拆分后的功能模块。
    """

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

    def clear_audit_logs(self) -> None:
        """清空审计日志"""
        self._access_logs.clear()

        audit_file = self._vault_path / "audit_log.jsonl"
        if audit_file.exists():
            try:
                audit_file.unlink()
                logger.info("Audit logs cleared")
            except Exception as e:
                logger.warning(f"Failed to delete audit log file: {e}")


__all__ = ["CredentialOpsMixin"]