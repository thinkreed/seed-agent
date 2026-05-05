"""
凭证保险库审计模块

包含访问日志记录、审计日志查询和使用统计功能。
"""

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.security.vault._types import CredentialAccessLog, CredentialRecord

logger = logging.getLogger(__name__)


class AuditMixin:
    """审计功能 Mixin 类

    提供访问日志记录、审计日志查询和使用统计功能。
    需要与 CredentialVault 配合使用，依赖 _access_logs, _credentials, _vault_path, _max_access_logs 属性。
    """

    _vault_path: Path
    _credentials: dict[str, "CredentialRecord"]
    _access_logs: list["CredentialAccessLog"]
    _max_access_logs: int

    def _log_access(
        self,
        credential_id: str,
        scope: str,
        requester_id: str | None,
        action: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """记录凭证访问"""
        from src.security.vault._types import CredentialAccessLog

        log_entry = CredentialAccessLog(
            timestamp=time.time(),
            credential_id=credential_id,
            scope=scope,
            requester_id=requester_id,
            action=action,
            success=success,
            error=error,
        )

        self._access_logs.append(log_entry)

        # 限制日志大小
        if len(self._access_logs) > self._max_access_logs:
            self._access_logs = self._access_logs[-self._max_access_logs :]

        # 持久化审计日志
        self._persist_audit_log()

    def get_access_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取访问审计日志

        Args:
            limit: 返回条数限制

        Returns:
            审计日志列表
        """
        logs = self._access_logs[-limit:]
        return [
            {
                "timestamp": log.timestamp,
                "credential_id": log.credential_id,
                "scope": log.scope,
                "requester_id": log.requester_id,
                "action": log.action,
                "success": log.success,
                "error": log.error,
            }
            for log in logs
        ]

    def get_credential_usage_stats(
        self, provider: str, credential_type: str
    ) -> dict[str, Any]:
        """获取凭证使用统计

        Args:
            provider: 提供商名称
            credential_type: 凭证类型

        Returns:
            使用统计数据
        """
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            return {}

        record = self._credentials[credential_id]

        # 过滤相关访问日志
        accesses = [
            log for log in self._access_logs if log.credential_id == credential_id
        ]

        return {
            "credential_id": credential_id,
            "provider": record.provider,
            "type": record.type,
            "total_access_count": record.access_count,
            "last_accessed": record.last_accessed,
            "created_at": record.created_at,
            "rotation_count": len(record.rotation_history),
            "last_rotated_at": record.rotated_at,
            "expiry": record.expiry,
            "recent_accesses": [
                {
                    "timestamp": log.timestamp,
                    "scope": log.scope,
                    "requester_id": log.requester_id,
                    "success": log.success,
                }
                for log in accesses[-10:]
            ],
            "success_rate": (
                sum(1 for a in accesses if a.success) / len(accesses) * 100
                if accesses
                else 100.0
            ),
        }

    def get_vault_stats(self) -> dict[str, Any]:
        """获取保险库统计信息"""
        total_accesses = len(self._access_logs)
        successful = sum(1 for log in self._access_logs if log.success)

        return {
            "vault_path": str(self._vault_path),
            "credentials_count": len(self._credentials),
            "access_logs_count": total_accesses,
            "encryption_enabled": hasattr(self, "_encryption_key")
            and self._encryption_key is not None,
            "total_accesses": total_accesses,
            "successful_accesses": successful,
            "failed_accesses": total_accesses - successful,
            "success_rate": (successful / total_accesses * 100)
            if total_accesses
            else 100.0,
        }