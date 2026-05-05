"""请求执行模块

负责代理执行外部请求（带超时和并发控制）
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from src.security.proxy._audit import persist_request_audit, sanitize_request_context
from src.security.proxy._client_factory import create_temp_client, destroy_temp_client
from src.security.proxy._error_handler import (
    handle_general_error,
    handle_permission_error,
    handle_value_error,
)
from src.security.proxy._temp_client import TemporaryClient
from src.security.proxy._types import RequestAuditLog

logger = logging.getLogger(__name__)


async def execute_external_request(
    vault: Any,
    provider: str,
    credential_type: str,
    request_func: Callable[[Any, dict[str, Any]], Any],
    request_context: dict[str, Any],
    requester_id: str | None,
    scope: str,
    timeout: float,
    semaphore: asyncio.Semaphore,
    log_callback: Callable[[RequestAuditLog], None],
    vault_path: Any,
) -> dict[str, Any]:
    """代理执行外部请求"""
    async with semaphore:
        start_time = time.time()
        temp_client: TemporaryClient | None = None

        try:
            credential = vault.get_credential(
                provider, credential_type, scope=scope, requester_id=requester_id
            )
            temp_client = await create_temp_client(provider, credential)

            return await _execute_with_timeout(
                temp_client, request_func, request_context, timeout,
                start_time, provider, credential_type, requester_id,
                log_callback, vault_path,
            )

        except PermissionError as e:
            return handle_permission_error(
                e, start_time, provider, credential_type,
                requester_id, request_context, log_callback, vault_path
            )

        except ValueError as e:
            return handle_value_error(
                e, start_time, provider, credential_type,
                requester_id, request_context, log_callback, vault_path
            )

        finally:
            if temp_client:
                destroy_temp_client(temp_client)


async def _execute_with_timeout(
    temp_client: TemporaryClient,
    request_func: Callable[[Any, dict[str, Any]], Any],
    request_context: dict[str, Any],
    timeout: float,
    start_time: float,
    provider: str,
    credential_type: str,
    requester_id: str | None,
    log_callback: Callable[[RequestAuditLog], None],
    vault_path: Any,
) -> dict[str, Any]:
    """执行请求（带超时处理）"""
    try:
        result = await asyncio.wait_for(
            request_func(temp_client.client, request_context),
            timeout=timeout,
        )

        duration_ms = (time.time() - start_time) * 1000

        log_entry = RequestAuditLog(
            timestamp=time.time(),
            provider=provider,
            credential_type=credential_type,
            requester_id=requester_id,
            status="success",
            duration_ms=duration_ms,
            request_context=sanitize_request_context(request_context),
        )
        log_callback(log_entry)
        persist_request_audit(log_entry, vault_path)

        return {"status": "success", "result": result, "duration_ms": duration_ms}

    except TimeoutError:
        duration_ms = (time.time() - start_time) * 1000

        log_entry = RequestAuditLog(
            timestamp=time.time(),
            provider=provider,
            credential_type=credential_type,
            requester_id=requester_id,
            status="timeout",
            duration_ms=duration_ms,
            request_context=sanitize_request_context(request_context),
            error=f"Request timeout after {timeout}s",
        )
        log_callback(log_entry)
        persist_request_audit(log_entry, vault_path)

        return {
            "status": "timeout",
            "error": f"Request timeout after {timeout}s",
            "duration_ms": duration_ms,
        }

    except Exception as e:
        return handle_general_error(
            e, start_time, provider, credential_type,
            requester_id, request_context, log_callback, vault_path
        )