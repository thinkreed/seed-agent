"""请求审计日志工具函数

提取敏感信息过滤和持久化逻辑。
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


__all__ = ["SENSITIVE_KEYS", "sanitize_request_context", "persist_request_audit"]