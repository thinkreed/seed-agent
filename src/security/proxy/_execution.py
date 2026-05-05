"""
请求执行模块

内部模块，负责代理执行外部请求。

核心功能:
- 创建和销毁临时客户端
- 执行外部请求（带超时和并发控制）
- 执行流式请求
- 请求审计日志记录
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from src.security.proxy._temp_client import TemporaryClient
from src.security.proxy._types import RequestAuditLog

logger = logging.getLogger(__name__)

# Provider 配置
PROVIDER_CONFIGS: dict[str, dict[str, str | None]] = {
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


async def create_temp_client(
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
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: {list(PROVIDER_CONFIGS.keys())}"
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
        except ImportError as e:
            raise ValueError(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            ) from e
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


def destroy_temp_client(temp_client: TemporaryClient) -> None:
    """销毁临时客户端

    凭证销毁: 客户端对象被丢弃，凭证不再可用
    """
    temp_client.destroy()

    logger.debug(
        f"Temporary client destroyed: provider={temp_client.provider}, "
        f"lifetime={temp_client.lifetime_ms:.2f}ms"
    )


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
    """代理执行外部请求

    流程:
    1. 从 Vault 获取临时凭证（作用域检查）
    2. 创建临时客户端（凭证不存储在 Sandbox）
    3. 执行请求
    4. 请求完成后，凭证销毁
    5. 记录审计日志

    Args:
        vault: CredentialVault 实例
        provider: 提供商名称
        credential_type: 凭证类型
        request_func: 请求执行函数
        request_context: 请求上下文
        requester_id: 请求者 ID
        scope: 请求作用域
        timeout: 请求超时时间
        semaphore: 并发控制信号量
        log_callback: 审计日志回调
        vault_path: Vault 路径（用于持久化审计）

    Returns:
        请求结果字典

    Raises:
        ValueError: 凭证不存在
        PermissionError: 作用域不允许
    """
    # 并发控制
    async with semaphore:
        start_time = time.time()
        temp_client: TemporaryClient | None = None

        try:
            # 1. 从 Vault 获取临时凭证（作用域检查）
            credential = vault.get_credential(
                provider,
                credential_type,
                scope=scope,
                requester_id=requester_id,
            )

            # 2. 创建临时客户端
            temp_client = await create_temp_client(provider, credential)

            # 3. 执行请求（带超时）
            try:
                result = await asyncio.wait_for(
                    request_func(temp_client.client, request_context),
                    timeout=timeout,
                )

                duration_ms = (time.time() - start_time) * 1000

                # 4. 记录成功审计
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

                return {
                    "status": "success",
                    "result": result,
                    "duration_ms": duration_ms,
                }

            except TimeoutError:
                duration_ms = (time.time() - start_time) * 1000

                # 记录超时审计
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

        except PermissionError as e:
            # 作用域不允许
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

        except ValueError as e:
            # 凭证不存在
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

        except Exception as e:
            # 其他异常
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

        finally:
            # 5. 销毁临时客户端（凭证清理）
            if temp_client:
                destroy_temp_client(temp_client)


async def execute_streaming_request(
    vault: Any,
    provider: str,
    credential_type: str,
    stream_func: Callable[[Any, dict[str, Any]], Any],
    request_context: dict[str, Any],
    requester_id: str | None,
    scope: str,
) -> tuple[Any, dict[str, Any]]:
    """代理执行流式请求

    Args:
        vault: CredentialVault 实例
        provider: 提供商名称
        credential_type: 凭证类型
        stream_func: 流式请求函数
        request_context: 请求上下文
        requester_id: 请求者 ID
        scope: 请求作用域

    Returns:
        (stream_iterator, metadata)
    """
    start_time = time.time()

    # 从 Vault 获取临时凭证
    credential = vault.get_credential(
        provider,
        credential_type,
        scope=scope,
        requester_id=requester_id,
    )

    # 创建临时客户端
    temp_client = await create_temp_client(provider, credential)

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
    metadata: dict[str, Any],
    status: str = "success",
    error: str | None = None,
    log_callback: Callable[[RequestAuditLog], None] | None = None,
    vault_path: Any = None,
) -> None:
    """完成流式请求（销毁凭证）

    Args:
        metadata: 流式请求元数据
        status: 请求状态
        error: 错误信息
        log_callback: 审计日志回调
        vault_path: Vault 路径（用于持久化审计）
    """
    duration_ms = (time.time() - metadata["start_time"]) * 1000

    # 记录审计
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

    # 销毁临时客户端
    temp_client = metadata.get("temp_client")
    if temp_client:
        destroy_temp_client(temp_client)


def sanitize_request_context(context: dict[str, Any]) -> dict[str, Any]:
    """过滤请求上下文中的敏感信息

    Args:
        context: 原始请求上下文

    Returns:
        过滤后的安全上下文
    """
    sensitive_keys = [
        "api_key",
        "apikey",
        "apiKey",
        "token",
        "secret",
        "password",
        "credential",
    ]

    safe_context: dict[str, Any] = {}
    for key, value in context.items():
        # Check both lowercase and original key
        key_lower = key.lower()
        if key_lower in sensitive_keys or key in sensitive_keys:
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
            import os

            os.chmod(audit_file, 0o600)
        except OSError:
            logger.warning(f"Failed to set permissions on audit file: {audit_file}")
    except Exception as e:
        logger.warning(f"Failed to persist request audit: {e}")


def get_supported_providers() -> list[str]:
    """获取支持的 Provider 列表"""
    return list(PROVIDER_CONFIGS.keys())


def register_provider(
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
    PROVIDER_CONFIGS[provider] = {
        "base_url": base_url,
        "client_class": client_class,
    }

    logger.info(f"Provider registered: {provider}, base_url={base_url}")