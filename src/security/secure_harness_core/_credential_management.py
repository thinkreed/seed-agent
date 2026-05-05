"""
凭证管理模块

提供凭证存储、轮换和统计查询功能：
- store_credential: 存储凭证到 Vault
- rotate_credential: 轮换凭证
- get_credential_usage_stats: 获取凭证使用统计

核心特性：
- 凭证安全存储
- 轮换历史追踪
- 使用统计查询
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CredentialManagementMixin:
    """凭证管理功能 Mixin

    提供 store_credential, rotate_credential, get_credential_usage_stats 方法。
    需要与 SecureHarness 配合使用，依赖 _vault, session 等属性。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        _vault: Any
        session: Any

    async def store_credential(
        self,
        provider: str,
        credential_type: str,
        credential_value: str,
        scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """存储凭证到 Vault

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            credential_value: 凭证值
            scopes: 允许的作用域
            metadata: 元数据

        Returns:
            credential_id
        """
        from src.security.credential_vault import CredentialScope

        return self._vault.store_credential(
            provider=provider,
            credential_type=credential_type,
            credential_value=credential_value,
            scopes=scopes or [CredentialScope.API_CALL.value],
            metadata=metadata,
        )

    async def rotate_credential(
        self,
        provider: str,
        credential_type: str,
        new_value: str,
        reason: str | None = None,
    ) -> None:
        """轮换凭证

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            new_value: 新凭证值
            reason: 轮换原因
        """
        self._vault.rotate_credential(
            provider=provider,
            credential_type=credential_type,
            new_value=new_value,
            rotated_by=self.session.session_id,
            reason=reason,
        )

    def get_credential_usage_stats(
        self,
        provider: str,
        credential_type: str,
    ) -> dict[str, Any]:
        """获取凭证使用统计

        Args:
            provider: 提供商名称
            credential_type: 凭证类型

        Returns:
            使用统计数据
        """
        return self._vault.get_credential_usage_stats(provider, credential_type)