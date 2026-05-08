"""请求审计日志管理器

管理请求审计日志的记录、持久化和查询。
"""

import logging
from pathlib import Path
from typing import Any

from src.security.proxy._audit_utils import persist_request_audit
from src.security.proxy._types import RequestAuditLog

logger = logging.getLogger(__name__)


class AuditLogManager:
    """审计日志管理器

    管理请求审计日志的记录、持久化和查询。
    """

    def __init__(self, vault_path: Path | None = None):
        """初始化审计日志管理器

        Args:
            vault_path: Vault 路径（可选）
        """
        self._vault_path = vault_path
        self._audit_entries: list[RequestAuditLog] = []
        self._request_logs: list[dict[str, Any]] = []  # 向后兼容

    def add_entry(self, entry: RequestAuditLog) -> None:
        """添加审计日志条目

        Args:
            entry: 审计日志条目
        """
        self._audit_entries.append(entry)

    def persist(self) -> None:
        """持久化所有审计日志"""
        if not self._vault_path:
            return

        for entry in self._audit_entries:
            persist_request_audit(entry, self._vault_path)

        self._audit_entries.clear()

    def get_entries(self) -> list[RequestAuditLog]:
        """获取所有审计日志条目"""
        return self._audit_entries.copy()

    def clear(self) -> None:
        """清空审计日志"""
        self._audit_entries.clear()
        self._request_logs.clear()  # 向后兼容

    def get_request_logs(self) -> list[dict[str, Any]]:
        """向后兼容：获取请求日志"""
        return self._request_logs.copy()

    def add_log(self, entry: RequestAuditLog) -> None:
        """添加审计日志（向后兼容别名）

        Args:
            entry: 审计日志条目
        """
        self.add_entry(entry)
        # 同时添加到向后兼容的列表
        self._request_logs.append({
            "timestamp": entry.timestamp,
            "provider": entry.provider,
            "credential_type": entry.credential_type,
            "requester_id": entry.requester_id,
            "status": entry.status,
            "duration_ms": entry.duration_ms,
            "request_context": entry.request_context,
            "error": entry.error,
        })

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取审计日志

        Args:
            limit: 最大返回数量

        Returns:
            日志列表
        """
        return self._request_logs[-limit:]

    def get_stats(self, active_clients: int = 0) -> dict[str, Any]:
        """获取请求统计信息

        Args:
            active_clients: 活跃客户端数量

        Returns:
            统计信息字典
        """
        total = len(self._request_logs)
        successful = sum(1 for log in self._request_logs if log.get("status") == "success")
        failed = sum(1 for log in self._request_logs if log.get("status") == "failed")
        timeout = sum(1 for log in self._request_logs if log.get("status") == "timeout")

        success_rate = (successful / total * 100) if total > 0 else 0.0

        return {
            "total_requests": total,
            "successful": successful,
            "failed": failed,
            "timeout": timeout,
            "success_rate": success_rate,
            "active_clients": active_clients,
        }


__all__ = ["AuditLogManager"]