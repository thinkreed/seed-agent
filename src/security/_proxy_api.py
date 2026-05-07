"""CredentialProxy API 辅助方法

职责:
- Provider 管理
- 清理和状态管理
"""

import logging
import time
from pathlib import Path
from typing import Any

from src.security.proxy import get_supported_providers, register_provider

logger = logging.getLogger(__name__)


def register_new_provider(
    provider: str,
    base_url: str | None,
    client_class: str = "AsyncOpenAI",
) -> None:
    """注册新的 Provider"""
    register_provider(provider, base_url, client_class)


def get_providers() -> list[str]:
    """获取支持的 Provider 列表"""
    return get_supported_providers()


def cleanup_expired_clients(
    active_clients: dict[str, Any],
    timeout_threshold: float = 300.0,
) -> int:
    """清理超时的活跃客户端

    Args:
        active_clients: 活跃客户端字典
        timeout_threshold: 超时阈值（秒）

    Returns:
        清理的客户端数量
    """
    now = time.time()

    expired_ids = [
        provider
        for provider, client in active_clients.items()
        if now - client.created_at > timeout_threshold
    ]

    for provider in expired_ids:
        client = active_clients[provider]
        client.destroy()
        del active_clients[provider]

    if expired_ids:
        logger.info(f"Cleaned up {len(expired_ids)} expired clients")

    return len(expired_ids)


def clear_audit_logs(vault_path: Path) -> None:
    """清空请求审计日志

    Args:
        vault_path: Vault 目录路径
    """
    audit_file = vault_path / "request_audit.jsonl"
    if audit_file.exists():
        try:
            audit_file.unlink()
            logger.info("Request audit logs cleared")
        except Exception as e:
            logger.warning(f"Failed to delete request audit file: {e}")


__all__ = [
    "cleanup_expired_clients",
    "clear_audit_logs",
    "get_providers",
    "register_new_provider",
]