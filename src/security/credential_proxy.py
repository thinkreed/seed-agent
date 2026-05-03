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
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from src.security.credential_vault import CredentialVault, CredentialScope

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class RequestAuditLog:
    """请求审计日志"""
    timestamp: float
    provider: str
    credential_type: str
    requester_id: str | None
    status: str  # success, failed, timeout
    duration_ms: float
    request_context: dict[str, Any]
    error: str | None = None


@dataclass
class TemporaryClient:
    """临时客户端（凭证销毁后不可用）"""
    provider: str
    client: Any
    credential: str
    created_at: float
    destroyed: bool = False

    def destroy(self) -> None:
        """销毁客户端（凭证清理）"""
        self.destroyed = True
        self.client = None
        self.credential = ""  # 清空凭证引用
        logger.debug(f"Temporary client destroyed for provider: {self.provider}")


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

    # Provider 配置
    PROVIDER_CONFIGS = {
        "openai": {
            "base_url": None,
            "client_class": "AsyncOpenAI",
        },
        "anthropic": {
            "base_url": None,
            "client_class": "AsyncAnthropic",
        },
        "bailian": {
            "base_url": "https://coding.dashscope.aliyuncs.com/v1",
            "client_class": "AsyncOpenAI",
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "client_class": "AsyncOpenAI",
        },
    }

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

        # 请求审计日志
        self._request_logs: list[RequestAuditLog] = []
        self._max_request_logs = 10000

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

        # 并发控制
        async with self._request_semaphore:
            start_time = time.time()
            temp_client: TemporaryClient | None = None

            try:
                # 1. 从 Vault 获取临时凭证（作用域检查）
                credential = self._vault.get_credential(
                    provider,
                    credential_type,
                    scope=scope,
                    requester_id=requester_id,
                )

                # 2. 创建临时客户端
                temp_client = await self._create_temp_client(provider, credential)
                self._active_clients[temp_client.provider] = temp_client

                # 3. 执行请求（带超时）
                try:
                    result = await asyncio.wait_for(
                        request_func(temp_client.client, request_context),
                        timeout=actual_timeout,
                    )

                    duration_ms = (time.time() - start_time) * 1000

                    # 4. 记录成功审计
                    self._log_request(
                        provider=provider,
                        credential_type=credential_type,
                        requester_id=requester_id,
                        status="success",
                        duration_ms=duration_ms,
                        request_context=request_context,
                    )

                    return {
                        "status": "success",
                        "result": result,
                        "duration_ms": duration_ms,
                    }

                except asyncio.TimeoutError:
                    duration_ms = (time.time() - start_time) * 1000

                    # 记录超时审计
                    self._log_request(
                        provider=provider,
                        credential_type=credential_type,
                        requester_id=requester_id,
                        status="timeout",
                        duration_ms=duration_ms,
                        request_context=request_context,
                        error=f"Request timeout after {actual_timeout}s",
                    )

                    return {
                        "status": "timeout",
                        "error": f"Request timeout after {actual_timeout}s",
                        "duration_ms": duration_ms,
                    }

            except PermissionError as e:
                # 作用域不允许
                duration_ms = (time.time() - start_time) * 1000
                self._log_request(
                    provider=provider,
                    credential_type=credential_type,
                    requester_id=requester_id,
                    status="failed",
                    duration_ms=duration_ms,
                    request_context=request_context,
                    error=str(e),
                )
                raise

            except ValueError as e:
                # 凭证不存在
                duration_ms = (time.time() - start_time) * 1000
                self._log_request(
                    provider=provider,
                    credential_type=credential_type,
                    requester_id=requester_id,
                    status="failed",
                    duration_ms=duration_ms,
                    request_context=request_context,
                    error=str(e),
                )
                raise

            except Exception as e:
                # 其他异常
                duration_ms = (time.time() - start_time) * 1000
                error_msg = f"{type(e).__name__}: {str(e)[:500]}"

                self._log_request(
                    provider=provider,
                    credential_type=credential_type,
                    requester_id=requester_id,
                    status="failed",
                    duration_ms=duration_ms,
                    request_context=request_context,
                    error=error_msg,
                )

                return {
                    "status": "failed",
                    "error": error_msg,
                    "duration_ms": duration_ms,
                }

            finally:
                # 5. 销毁临时客户端（凭证清理）
                if temp_client:
                    self._destroy_temp_client(temp_client)
                    if temp_client.provider in self._active_clients:
                        del self._active_clients[temp_client.provider]

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
        start_time = time.time()

        # 从 Vault 获取临时凭证
        credential = self._vault.get_credential(
            provider,
            credential_type,
            scope=scope,
            requester_id=requester_id,
        )

        # 创建临时客户端
        temp_client = await self._create_temp_client(provider, credential)

        # 执行流式请求
        stream = await stream_func(temp_client.client, request_context)

        # 返回流和元数据（客户端将在流结束后销毁）
        metadata = {
            "provider": provider,
            "requester_id": requester_id,
            "temp_client": temp_client,
            "start_time": start_time,
        }

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
        duration_ms = (time.time() - metadata["start_time"]) * 1000

        # 记录审计
        self._log_request(
            provider=metadata["provider"],
            credential_type="api_key",
            requester_id=metadata["requester_id"],
            status=status,
            duration_ms=duration_ms,
            request_context={},
            error=error,
        )

        # 销毁临时客户端
        temp_client = metadata.get("temp_client")
        if temp_client:
            self._destroy_temp_client(temp_client)

    async def _create_temp_client(
        self,
        provider: str,
        credential: str,
    ) -> TemporaryClient:
        """创建临时客户端

        重要: 客户端不存储在 Sandbox 中

        Args:
            provider: 提供商名称
            credential: 凭证值

        Returns:
            TemporaryClient 实例

        Raises:
            ValueError: Provider 不支持
        """
        config = self.PROVIDER_CONFIGS.get(provider)
        if not config:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {list(self.PROVIDER_CONFIGS.keys())}"
            )

        client_class = config["client_class"]
        base_url = config.get("base_url")

        # 创建客户端实例
        if client_class == "AsyncOpenAI":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=credential,
                base_url=base_url,
            )
        elif client_class == "AsyncAnthropic":
            try:
                from anthropic import AsyncAnthropic
                client = AsyncAnthropic(api_key=credential)
            except ImportError:
                raise ValueError(
                    "anthropic package not installed. "
                    "Install with: pip install anthropic"
                )
        else:
            raise ValueError(f"Unsupported client class: {client_class}")

        temp_client = TemporaryClient(
            provider=provider,
            client=client,
            credential=credential,
            created_at=time.time(),
        )

        logger.debug(
            f"Temporary client created: provider={provider}, "
            f"base_url={base_url or 'default'}"
        )

        return temp_client

    def _destroy_temp_client(self, temp_client: TemporaryClient) -> None:
        """销毁临时客户端

        凭证销毁: 客户端对象被丢弃，凭证不再可用
        """
        temp_client.destroy()

        logger.debug(
            f"Temporary client destroyed: provider={temp_client.provider}, "
            f"lifetime={(time.time() - temp_client.created_at) * 1000:.2f}ms"
        )

    # === 审计日志 ===

    def _log_request(
        self,
        provider: str,
        credential_type: str,
        requester_id: str | None,
        status: str,
        duration_ms: float,
        request_context: dict[str, Any],
        error: str | None = None,
    ) -> None:
        """记录请求审计"""
        # 过滤敏感信息
        safe_context = self._sanitize_request_context(request_context)

        log_entry = RequestAuditLog(
            timestamp=time.time(),
            provider=provider,
            credential_type=credential_type,
            requester_id=requester_id,
            status=status,
            duration_ms=duration_ms,
            request_context=safe_context,
            error=error,
        )

        self._request_logs.append(log_entry)

        # 限制日志大小
        if len(self._request_logs) > self._max_request_logs:
            self._request_logs = self._request_logs[-self._max_request_logs:]

        # 持久化审计日志
        self._persist_request_audit(log_entry)

    def _sanitize_request_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """过滤请求上下文中的敏感信息"""
        sensitive_keys = ["api_key", "apikey", "apiKey", "token", "secret", "password", "credential"]

        safe_context: dict[str, Any] = {}
        for key, value in context.items():
            # Check both lowercase and original key
            key_lower = key.lower()
            if key_lower in sensitive_keys or key in sensitive_keys:
                safe_context[key] = "[REDACTED]"
            elif isinstance(value, dict):
                safe_context[key] = self._sanitize_request_context(value)
            elif isinstance(value, str) and len(value) > 100:
                safe_context[key] = value[:100] + "...[truncated]"
            else:
                safe_context[key] = value

        return safe_context

    def _persist_request_audit(self, log_entry: RequestAuditLog) -> None:
        """持久化请求审计日志"""
        audit_file = self._vault._vault_path / "request_audit.jsonl"

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
        except Exception as e:
            logger.warning(f"Failed to persist request audit: {e}")

    def get_request_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取请求审计日志

        Args:
            limit: 返回条数限制

        Returns:
            审计日志列表
        """
        logs = self._request_logs[-limit:]
        return [
            {
                "timestamp": log.timestamp,
                "provider": log.provider,
                "credential_type": log.credential_type,
                "requester_id": log.requester_id,
                "status": log.status,
                "duration_ms": log.duration_ms,
                "request_context": log.request_context,
                "error": log.error,
            }
            for log in logs
        ]

    def get_request_stats(self) -> dict[str, Any]:
        """获取请求统计信息"""
        total_requests = len(self._request_logs)
        successful = sum(1 for log in self._request_logs if log.status == "success")
        failed = sum(1 for log in self._request_logs if log.status == "failed")
        timeouts = sum(1 for log in self._request_logs if log.status == "timeout")

        # 按 Provider 统计
        by_provider: dict[str, dict[str, int]] = {}
        for log in self._request_logs:
            if log.provider not in by_provider:
                by_provider[log.provider] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "timeout": 0,
                }
            by_provider[log.provider]["total"] += 1
            by_provider[log.provider][log.status] += 1

        # 平均耗时
        durations = [log.duration_ms for log in self._request_logs]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total_requests": total_requests,
            "successful": successful,
            "failed": failed,
            "timeouts": timeouts,
            "success_rate": (successful / total_requests * 100) if total_requests else 100.0,
            "average_duration_ms": avg_duration,
            "by_provider": by_provider,
            "active_clients": len(self._active_clients),
            "max_concurrent_requests": self._max_concurrent_requests,
        }

    # === Provider 管理 ===

    def register_provider(
        self,
        provider: str,
        base_url: str | None,
        client_class: str = "AsyncOpenAI",
    ) -> None:
        """注册新的 Provider

        Args:
            provider: Provider 名称
            base_url: API 基础 URL
            client_class: 客户端类名
        """
        self.PROVIDER_CONFIGS[provider] = {
            "base_url": base_url,
            "client_class": client_class,
        }

        logger.info(f"Provider registered: {provider}, base_url={base_url}")

    def get_supported_providers(self) -> list[str]:
        """获取支持的 Provider 列表"""
        return list(self.PROVIDER_CONFIGS.keys())

    # === 清理 ===

    def clear_request_logs(self) -> None:
        """清空请求审计日志"""
        self._request_logs.clear()

        # 删除日志文件
        audit_file = self._vault._vault_path / "request_audit.jsonl"
        if audit_file.exists():
            try:
                audit_file.unlink()
                logger.info("Request audit logs cleared")
            except Exception as e:
                logger.warning(f"Failed to delete request audit file: {e}")

    def cleanup_active_clients(self) -> int:
        """清理超时的活跃客户端

        Returns:
            清理的客户端数量
        """
        timeout_threshold = 300.0  # 5 分钟超时
        now = time.time()

        expired_ids = [
            provider for provider, client in self._active_clients.items()
            if now - client.created_at > timeout_threshold
        ]

        for provider in expired_ids:
            client = self._active_clients[provider]
            self._destroy_temp_client(client)
            del self._active_clients[provider]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired clients")

        return len(expired_ids)