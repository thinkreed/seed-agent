"""凭证代理 - CredentialProxy

基于 Harness Engineering "凭证永不进沙盒" 设计：
- 所有外部请求必须通过代理执行
- 从 Vault 按需获取凭证
- 请求完成后凭证立即销毁

子模块架构:
- proxy/_types.py: RequestAuditLog 类型
- proxy/_temp_client.py: TemporaryClient
- proxy/_execution.py: 执行方法
- proxy/_audit.py: 审计日志管理
- proxy/_streaming.py: 流式请求
- _proxy_api.py: Provider 管理和清理辅助方法
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from src.security._proxy_api import (
    cleanup_expired_clients,
    clear_audit_logs,
    get_providers,
    register_new_provider,
)
from src.security.credential_vault import CredentialScope, CredentialVault
from src.security.proxy import (
    AuditLogManager,
    RequestAuditLog,
    TemporaryClient,
    execute_external_request,
    execute_streaming_request,
    finalize_streaming_request,
)

logger = logging.getLogger(__name__)


class CredentialProxy:
    """凭证代理

    所有外部请求必须通过代理执行，凭证在请求完成后销毁。
    """

    def __init__(
        self,
        vault: CredentialVault,
        max_concurrent_requests: int = 10,
        request_timeout: float = 60.0,
    ):
        self._vault = vault
        self._max_concurrent_requests = max_concurrent_requests
        self._request_timeout = request_timeout
        self._audit_manager = AuditLogManager()
        self._request_logs = self._audit_manager._request_logs  # 向后兼容
        self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._active_clients: dict[str, TemporaryClient] = {}
        logger.info(f"CredentialProxy initialized: max_concurrent={max_concurrent_requests}")

    async def execute_external_request(
        self,
        provider: str,
        credential_type: str,
        request_func: Callable[[Any, dict[str, Any]], Any],
        request_context: dict[str, Any],
        requester_id: str | None = None,
        scope: str = CredentialScope.API_CALL.value,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """代理执行外部请求"""
        return await execute_external_request(
            vault=self._vault,
            provider=provider,
            credential_type=credential_type,
            request_func=request_func,
            request_context=request_context,
            requester_id=requester_id,
            scope=scope,
            timeout=timeout or self._request_timeout,
            semaphore=self._request_semaphore,
            log_callback=self._audit_manager.add_log,
            vault_path=self._vault._vault_path,
        )

    async def execute_streaming_request(
        self,
        provider: str,
        credential_type: str,
        stream_func: Callable[[Any, dict[str, Any]], Any],
        request_context: dict[str, Any],
        requester_id: str | None = None,
        scope: str = CredentialScope.API_CALL.value,
    ) -> tuple[Any, dict[str, Any]]:
        """代理执行流式请求"""
        stream, metadata = await execute_streaming_request(
            vault=self._vault,
            provider=provider,
            credential_type=credential_type,
            stream_func=stream_func,
            request_context=request_context,
            requester_id=requester_id,
            scope=scope,
        )
        temp_client = metadata.get("temp_client")
        if temp_client:
            self._active_clients[temp_client.provider] = temp_client
        return stream, metadata

    def finalize_streaming_request(
        self,
        metadata: dict[str, Any],
        status: str = "success",
        error: str | None = None,
    ) -> None:
        """完成流式请求（销毁凭证）"""
        finalize_streaming_request(
            metadata=metadata,
            status=status,
            error=error,
            log_callback=self._audit_manager.add_log,
            vault_path=self._vault._vault_path,
        )
        temp_client = metadata.get("temp_client")
        if temp_client and temp_client.provider in self._active_clients:
            del self._active_clients[temp_client.provider]

    def get_request_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取请求审计日志"""
        return self._audit_manager.get_logs(limit)

    def get_request_stats(self) -> dict[str, Any]:
        """获取请求统计信息"""
        return self._audit_manager.get_stats(len(self._active_clients))

    def _sanitize_request_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """过滤请求上下文中的敏感信息（向后兼容）"""
        from src.security.proxy._audit import sanitize_request_context
        return sanitize_request_context(context)

    def register_provider(self, provider: str, base_url: str | None, client_class: str = "AsyncOpenAI") -> None:
        """注册新的 Provider"""
        register_new_provider(provider, base_url, client_class)

    def get_supported_providers(self) -> list[str]:
        """获取支持的 Provider 列表"""
        return get_providers()

    def clear_request_logs(self) -> None:
        """清空请求审计日志"""
        self._audit_manager.clear()
        clear_audit_logs(self._vault._vault_path)

    def cleanup_active_clients(self) -> int:
        """清理超时的活跃客户端"""
        return cleanup_expired_clients(self._active_clients)


__all__ = ["CredentialProxy", "RequestAuditLog", "TemporaryClient"]