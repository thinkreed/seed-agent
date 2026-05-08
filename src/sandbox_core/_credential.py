"""Sandbox 凭证代理模块

处理凭证代理设置和凭证获取。
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CredentialProxyMixin:
    """凭证代理 mixin

    提供凭证代理设置和凭证获取方法。
    子类需要提供:
    - _credential_proxy: Any | None
    """

    _credential_proxy: Any | None

    def set_credential_proxy(self: Any, proxy: Any) -> None:
        """设置凭证代理

        Args:
            proxy: 凭证代理对象，需实现 get_credential(name) -> str | None
        """
        self._credential_proxy = proxy
        logger.info("Credential proxy set")

    def get_credential(self: Any, credential_name: str) -> str | None:
        """通过代理获取凭证

        Args:
            credential_name: 凭证名称

        Returns:
            凭证值，如果未设置代理或凭证不存在则返回 None
        """
        if self._credential_proxy:
            return self._credential_proxy.get_credential(credential_name)
        return None


__all__ = ["CredentialProxyMixin"]