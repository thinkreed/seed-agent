"""请求审计日志模块

负责记录和持久化请求审计日志
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.security.proxy._types import RequestAuditLog

logger = logging.getLogger(__name__)

# 敏感信息键列表
SENSITIVE_KEYS = [
    "api_key",
    "apikey",
    "apiKey",
    "token",
    "secret",
    "password",
    "credential",
]


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


def sanitize_request_context(context: dict[str, Any]) -> dict[str, Any]:
    """过滤请求上下文中的敏感信息

    Args:
        context: 原始请求上下文

    Returns:
        过滤后的安全上下文
    """
    safe_context: dict[str, Any] = {}
    for key, value in context.items():
        # Check both lowercase and original key
        key_lower = key.lower()
        if key_lower in SENSITIVE_KEYS or key in SENSITIVE_KEYS:
            safe_context[key] = "[REDACTED]"
        elif isinstance(value, dict):
            safe_context[key] = sanitize_request_context(value)
        elif isinstance(value, str) and len(value) > 100:
            safe_context[key] = value[:100] + "...[truncated]"
        else:
            safe_context[key] = value

    return safe_context


def persist_request_audit(log_entry: RequestAuditLog, vault_path: Any) -> None:
    """持久化请求审计日志（带文件权限保护）

    Args:
        log_entry: 审计日志条目
        vault_path: Vault 路径
    """
    audit_file = vault_path / "request_audit.jsonl"

    entry = {
        "timestamp": log_entry.timestamp,
        "provider": log_entry.provider,
        "credential_type": log_entry.credential_type,
        "requester_id": log_entry.requester_id,
        "status": log_entry.status,
        "duration_ms": log_entry.duration_ms,
        "request_context": log_entry.request_context,
        "error": log_entry.error,
    }

    try:
        with open(audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        # 安全：设置审计日志文件权限（仅 owner 可读写）
        try:
            os.chmod(audit_file, 0o600)
        except OSError:
            logger.warning(f"Failed to set permissions on audit file: {audit_file}")
    except Exception as e:
        logger.warning(f"Failed to persist request audit: {e}")