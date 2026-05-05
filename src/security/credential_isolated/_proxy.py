"""
凭证隔离沙盒 - 凭证代理集成模块

负责:
- 通过代理安全获取凭证
- 通过代理执行外部请求
- 凭证代理管理
"""

import logging
from typing import Any

from src.security.credential_proxy import CredentialProxy

logger = logging.getLogger(__name__)


async def get_credential_via_proxy(
    proxy: CredentialProxy | None,
    provider: str,
    credential_type: str,
    scope: str = "api_call",
    requester_id: str | None = None,
) -> str | None:
    """通过代理获取凭证

    注意：此方法仅供 Sandbox 内部使用，
    凭证不会暴露给执行代码。

    Args:
        proxy: 凭证代理实例
        provider: 提供商名称
        credential_type: 凭证类型
        scope: 请求作用域
        requester_id: 请求者 ID

    Returns:
        凭证值（内部使用，不暴露给代码）
    """
    if not proxy:
        logger.warning("No credential proxy configured")
        return None

    try:
        return proxy._vault.get_credential(
            provider,
            credential_type,
            scope=scope,
            requester_id=requester_id,
        )
    except Exception as e:
        logger.exception(f"Failed to get credential via proxy: {e}")
        return None


async def execute_external_request_via_proxy(
    proxy: CredentialProxy | None,
    provider: str,
    credential_type: str,
    request_func: Any,
    request_context: dict[str, Any],
    requester_id: str | None = None,
) -> dict[str, Any]:
    """通过代理执行外部请求

    Sandbox 内代码无法直接访问凭证，
    必须通过代理执行外部 API 请求。

    Args:
        proxy: 凭证代理实例
        provider: 提供商名称
        credential_type: 凭证类型
        request_func: 请求函数
        request_context: 请求上下文
        requester_id: 请求者 ID

    Returns:
        请求结果
    """
    if not proxy:
        return {
            "status": "failed",
            "error": "No credential proxy configured",
        }

    return await proxy.execute_external_request(
        provider=provider,
        credential_type=credential_type,
        request_func=request_func,
        request_context=request_context,
        requester_id=requester_id,
    )


class CredentialProxyManager:
    """凭证代理管理器

    管理凭证代理的生命周期和状态。
    """

    def __init__(self, proxy: CredentialProxy | None = None):
        self._proxy = proxy

    def set_proxy(self, proxy: CredentialProxy) -> None:
        """设置凭证代理"""
        self._proxy = proxy
        logger.info("Credential proxy set for isolated sandbox")

    def get_proxy(self) -> CredentialProxy | None:
        """获取当前凭证代理"""
        return self._proxy

    def is_enabled(self) -> bool:
        """检查凭证代理是否启用"""
        return self._proxy is not None

    async def get_credential(
        self,
        provider: str,
        credential_type: str,
        scope: str = "api_call",
        requester_id: str | None = None,
    ) -> str | None:
        """获取凭证（委托）"""
        return await get_credential_via_proxy(
            self._proxy, provider, credential_type, scope, requester_id
        )

    async def execute_request(
        self,
        provider: str,
        credential_type: str,
        request_func: Any,
        request_context: dict[str, Any],
        requester_id: str | None = None,
    ) -> dict[str, Any]:
        """执行外部请求（委托）"""
        return await execute_external_request_via_proxy(
            self._proxy, provider, credential_type,
            request_func, request_context, requester_id
        )