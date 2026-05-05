"""
凭证代理 - CredentialProxy

基于 Harness Engineering "凭证永不进沙盒" 设计理念：
- 所有外部请求必须通过代理执行
- 从 Vault 按需获取凭证
- 请求完成后凭证立即销毁
- 凭证始终不暴露给 Sandbox
- 所有外部调用可审计

核心特性:
- 代理执行外部请求
- 临时客户端创建（凭证不存储在 Sandbox）
- 凭证自动销毁（请求完成后清理）
- 请求审计日志
- 支持多种 Provider

参考来源: Harness Engineering "凭证永不进沙盒"

重构说明:
- RequestAuditLog 已移至 proxy/_types.py
- TemporaryClient 已移至 proxy/_temp_client.py
- 执行方法已移至 proxy/_execution.py
- 审计日志管理已移至 proxy/_audit.py
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from src.security.credential_vault import CredentialScope, CredentialVault
from src.security.proxy import (
    AuditLogManager,
    RequestAuditLog,
    TemporaryClient,
    execute_external_request,
    execute_streaming_request,
    finalize_streaming_request,
    get_supported_providers,
    register_provider,
)

logger = logging.getLogger(__name__)


class CredentialProxy:
    """凭证代理

    所有外部请求必须通过代理执行，凭证在请求完成后销毁。

    核心职责:
    1. 代理执行外部请求（凭证不暴露给 Sandbox）
    2. 从 Vault 按需获取临时凭证
    3. 创建临时客户端（请求完成后销毁）
    4. 请求审计日志（所有外部调用可追溯）

    安全特性:
    - 凭证不存储：客户端不持久化，凭证不暴露
    - 自动销毁：请求完成后立即清理临时客户端
    - 完整审计：记录所有请求详情

    Example:
        vault = CredentialVault()
        vault.store_credential("openai", "api_key", "sk-test123")

        proxy = CredentialProxy(vault)

        # 代理执行请求
        result = await proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=lambda client, ctx: client.chat.completions.create(**ctx),
            request_context={"model": "gpt-4", "messages": [...]},
            requester_id="session_001"
        )

        # 凭证已销毁，无法复用客户端
    """

    def __init__(
        self,
        vault: CredentialVault,
        max_concurrent_requests: int = 10,
        request_timeout: float = 60.0,
    ):
        """初始化凭证代理

        Args:
            vault: CredentialVault 实例
            max_concurrent_requests: 最大并发请求数
            request_timeout: 请求超时时间（秒）
        """
        self._vault = vault
        self._max_concurrent_requests = max_concurrent_requests
        self._request_timeout = request_timeout

        # 审计日志管理器
        self._audit_manager = AuditLogManager()

        # 向后兼容：_request_logs 代理到 _audit_manager._request_logs
        self._request_logs = self._audit_manager._request_logs

        # 并发控制
        self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)

        # 活跃临时客户端（用于追踪）
        self._active_clients: dict[str, TemporaryClient] = {}

        logger.info(
            f"CredentialProxy initialized: "
            f"max_concurrent={max_concurrent_requests}, "
            f"timeout={request_timeout}s"
        )

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
        """代理执行外部请求

        流程:
        1. 从 Vault 获取临时凭证（作用域检查）
        2. 创建临时客户端（凭证不存储在 Sandbox）
        3. 执行请求
        4. 请求完成后，凭证销毁
        5. 记录审计日志

        Args:
            provider: 提供商名称 (如 "openai", "bailian")
            credential_type: 凭证类型 (如 "api_key")
            request_func: 请求执行函数 (client, context) -> result
            request_context: 请求上下文（不含凭证）
            requester_id: 请求者 ID (用于审计)
            scope: 请求作用域（默认 api_call）
            timeout: 请求超时时间（秒）

        Returns:
            请求结果:
                {"status": "success", "result": ...}
                {"status": "failed", "error": ...}
                {"status": "timeout", "error": ...}

        Raises:
            ValueError: Provider 不支持
            PermissionError: 作用域不允许
        """
        actual_timeout = timeout or self._request_timeout

        return await execute_external_request(
            vault=self._vault,
            provider=provider,
            credential_type=credential_type,
            request_func=request_func,
            request_context=request_context,
            requester_id=requester_id,
            scope=scope,
            timeout=actual_timeout,
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
        timeout: float | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """代理执行流式请求

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            stream_func: 流式请求函数
            request_context: 请求上下文
            requester_id: 请求者 ID
            scope: 请求作用域
            timeout: 请求超时时间

        Returns:
            (stream_iterator, metadata)
        """
        stream, metadata = await execute_streaming_request(
            vault=self._vault,
            provider=provider,
            credential_type=credential_type,
            stream_func=stream_func,
            request_context=request_context,
            requester_id=requester_id,
            scope=scope,
        )

        # 注册活跃客户端
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
        """完成流式请求（销毁凭证）

        Args:
            metadata: 流式请求元数据
            status: 请求状态
            error: 错误信息
        """
        finalize_streaming_request(
            metadata=metadata,
            status=status,
            error=error,
            log_callback=self._audit_manager.add_log,
            vault_path=self._vault._vault_path,
        )

        # 清理活跃客户端记录
        temp_client = metadata.get("temp_client")
        if temp_client and temp_client.provider in self._active_clients:
            del self._active_clients[temp_client.provider]

    # === 审计日志 ===

    def _sanitize_request_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """过滤请求上下文中的敏感信息（向后兼容）

        Args:
            context: 原始请求上下文

        Returns:
            过滤后的安全上下文
        """
        from src.security.proxy._execution import sanitize_request_context

        return sanitize_request_context(context)

    def get_request_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取请求审计日志"""
        return self._audit_manager.get_logs(limit)

    def get_request_stats(self) -> dict[str, Any]:
        """获取请求统计信息"""
        return self._audit_manager.get_stats(len(self._active_clients))

    # === Provider 管理 ===

    def register_provider(
        self,
        provider: str,
        base_url: str | None,
        client_class: str = "AsyncOpenAI",
    ) -> None:
        """注册新的 Provider"""
        register_provider(provider, base_url, client_class)

    def get_supported_providers(self) -> list[str]:
        """获取支持的 Provider 列表"""
        return get_supported_providers()

    # === 清理 ===

    def clear_request_logs(self) -> None:
        """清空请求审计日志"""
        self._audit_manager.clear()

        # 删除日志文件
        audit_file = self._vault._vault_path / "request_audit.jsonl"
        if audit_file.exists():
            try:
                audit_file.unlink()
                logger.info("Request audit logs cleared")
            except Exception as e:
                logger.warning(f"Failed to delete request audit file: {e}")

    def cleanup_active_clients(self) -> int:
        """清理超时的活跃客户端"""
        timeout_threshold = 300.0  # 5 分钟超时
        now = time.time()

        expired_ids = [
            provider
            for provider, client in self._active_clients.items()
            if now - client.created_at > timeout_threshold
        ]

        for provider in expired_ids:
            client = self._active_clients[provider]
            client.destroy()
            del self._active_clients[provider]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired clients")

        return len(expired_ids)


# 导出公共 API（向后兼容）
__all__ = [
    "CredentialProxy",
    "RequestAuditLog",
    "TemporaryClient",
]