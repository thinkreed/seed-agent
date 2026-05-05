"""请求执行错误处理

错误处理辅助函数
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from src.security.proxy._audit import (
    persist_request_audit,
    sanitize_request_context,
)
from src.security.proxy._types import RequestAuditLog

logger = logging.getLogger(__name__)


def handle_permission_error(
    e: PermissionError,
    start_time: float,
    provider: str,
    credential_type: str,
    requester_id: str | None,
    request_context: dict[str, Any],
    log_callback: Callable[[RequestAuditLog], None],
    vault_path: Any,
) -> dict[str, Any]:
    """处理权限错误"""
    duration_ms = (time.time() - start_time) * 1000
    log_entry = RequestAuditLog(
        timestamp=time.time(),
        provider=provider,
        credential_type=credential_type,
        requester_id=requester_id,
        status="failed",
        duration_ms=duration_ms,
        request_context=sanitize_request_context(request_context),
        error=str(e),
    )
    log_callback(log_entry)
    persist_request_audit(log_entry, vault_path)
    raise


def handle_value_error(
    e: ValueError,
    start_time: float,
    provider: str,
    credential_type: str,
    requester_id: str | None,
    request_context: dict[str, Any],
    log_callback: Callable[[RequestAuditLog], None],
    vault_path: Any,
) -> dict[str, Any]:
    """处理值错误"""
    duration_ms = (time.time() - start_time) * 1000
    log_entry = RequestAuditLog(
        timestamp=time.time(),
        provider=provider,
        credential_type=credential_type,
        requester_id=requester_id,
        status="failed",
        duration_ms=duration_ms,
        request_context=sanitize_request_context(request_context),
        error=str(e),
    )
    log_callback(log_entry)
    persist_request_audit(log_entry, vault_path)
    raise


def handle_general_error(
    e: Exception,
    start_time: float,
    provider: str,
    credential_type: str,
    requester_id: str | None,
    request_context: dict[str, Any],
    log_callback: Callable[[RequestAuditLog], None],
    vault_path: Any,
) -> dict[str, Any]:
    """处理通用异常"""
    duration_ms = (time.time() - start_time) * 1000
    error_msg = f"{type(e).__name__}: {str(e)[:500]}"

    log_entry = RequestAuditLog(
        timestamp=time.time(),
        provider=provider,
        credential_type=credential_type,
        requester_id=requester_id,
        status="failed",
        duration_ms=duration_ms,
        request_context=sanitize_request_context(request_context),
        error=error_msg,
    )
    log_callback(log_entry)
    persist_request_audit(log_entry, vault_path)

    return {
        "status": "failed",
        "error": error_msg,
        "duration_ms": duration_ms,
    }