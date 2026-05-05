"""流式请求执行模块

负责代理执行流式请求
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from src.security.proxy._audit import persist_request_audit
from src.security.proxy._client_factory import create_temp_client, destroy_temp_client
from src.security.proxy._types import RequestAuditLog

logger = logging.getLogger(__name__)


async def execute_streaming_request(
    vault: Any,
    provider: str,
    credential_type: str,
    stream_func: Callable[[Any, dict[str, Any]], Any],
    request_context: dict[str, Any],
    requester_id: str | None,
    scope: str,
) -> tuple[Any, dict[str, Any]]:
    """代理执行流式请求"""
    start_time = time.time()

    credential = vault.get_credential(
        provider, credential_type, scope=scope, requester_id=requester_id
    )

    temp_client = await create_temp_client(provider, credential)
    stream = await stream_func(temp_client.client, request_context)

    metadata = {
        "provider": provider,
        "requester_id": requester_id,
        "temp_client": temp_client,
        "start_time": start_time,
    }

    return stream, metadata


def finalize_streaming_request(
    metadata: dict[str, Any],
    status: str = "success",
    error: str | None = None,
    log_callback: Callable[[RequestAuditLog], None] | None = None,
    vault_path: Any = None,
) -> None:
    """完成流式请求（销毁凭证）"""
    duration_ms = (time.time() - metadata["start_time"]) * 1000

    log_entry = RequestAuditLog(
        timestamp=time.time(),
        provider=metadata["provider"],
        credential_type="api_key",
        requester_id=metadata["requester_id"],
        status=status,
        duration_ms=duration_ms,
        request_context={},
        error=error,
    )

    if log_callback:
        log_callback(log_entry)

    if vault_path:
        persist_request_audit(log_entry, vault_path)

    temp_client = metadata.get("temp_client")
    if temp_client:
        destroy_temp_client(temp_client)