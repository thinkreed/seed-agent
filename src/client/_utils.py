"""
客户端工具函数模块

提供:
- _calc_duration_ms: 计算耗时
- _estimate_stream_tokens: 估算流式 token 数
- _resolve_api_key: API Key 解析（支持环境变量和 CredentialVault）
"""

import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.security.credential_vault import CredentialVault as CredentialVaultType


def _calc_duration_ms(start_time: float) -> float:
    """计算耗时（毫秒）

    Args:
        start_time: 开始时间（time.time() 返回值）

    Returns:
        耗时（毫秒）
    """
    return (time.time() - start_time) * 1000


def _estimate_stream_tokens(chunk_count: int) -> int:
    """估算流式响应 token 数

    粗略估算：每个 chunk 约 10 tokens

    Args:
        chunk_count: chunk 数量

    Returns:
        估算的 token 数
    """
    return chunk_count * 10


def _resolve_api_key(
    api_key: str,
    vault: "CredentialVaultType | None" = None,
    provider: str | None = None,
) -> str:
    """解析 API Key，支持环境变量引用和 CredentialVault

    凭证获取优先级：
    1. 如果 vault 配置且 provider 存储在 vault 中 → 从 vault 获取
    2. 环境变量引用 (${ENV_VAR}) → 从环境变量获取
    3. 直接值 → 返回原始值

    Args:
        api_key: API Key 配置值（可能是 ${ENV_VAR} 或直接值）
        vault: CredentialVault 实例（可选）
        provider: Provider 名称（用于从 vault 获取）

    Returns:
        解析后的 API Key

    Raises:
        RuntimeError: Vault 获取失败时抛出异常
    """
    # 优先从 Vault 获取
    if vault and provider:
        try:
            if vault.has_credential(provider, "api_key"):
                return vault.get_credential(
                    provider,
                    "api_key",
                    scope="api_call",
                    requester_id="llm_gateway_init",
                )
        except Exception as e:
            # Vault 获取失败时抛出异常，而非静默继续
            # 避免空 API key 被传递给客户端导致后续请求全部失败
            raise RuntimeError(
                f"Failed to get credential from vault for {provider}: {type(e).__name__}: {e}"
            ) from e

    # 环境变量引用
    if api_key.startswith("${") and api_key.endswith("}"):
        env_var = api_key[2:-1]
        return os.environ.get(env_var, "").strip()

    # 直接值
    return api_key.strip()
