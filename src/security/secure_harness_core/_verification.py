"""
验证方法模块

提供凭证安全和 Vault 状态验证功能：
- verify_credential_isolation: 验证凭证隔离有效性
- verify_vault_integrity: 验证 Vault 工作正常

核心特性：
- Sandbox 隔离验证
- Vault 存取测试
- 安全机制完整性检查
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VerificationMixin:
    """验证功能 Mixin

    提供 verify_credential_isolation 和 verify_vault_integrity 方法。
    需要与 SecureHarness 配合使用，依赖 sandbox, _vault 等属性。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        sandbox: Any
        _vault: Any

    async def verify_credential_isolation(self) -> dict[str, Any]:
        """验证凭证隔离是否有效

        Returns:
            验证结果
        """
        from src.security.credential_isolated_sandbox import CredentialIsolatedSandbox

        if isinstance(self.sandbox, CredentialIsolatedSandbox):
            return await self.sandbox.verify_credential_isolation()

        return {
            "isolation_verified": False,
            "reason": "Sandbox is not CredentialIsolatedSandbox",
        }

    async def verify_vault_integrity(self) -> dict[str, Any]:
        """验证 Vault 是否正常工作

        Returns:
            验证结果
        """
        from src.security.credential_vault import CredentialScope

        try:
            # 测试存储和获取
            self._vault.store_credential(
                provider="_test",
                credential_type="api_key",
                credential_value="test_value_123",
                scopes=[CredentialScope.API_CALL.value],
                metadata={"test": True},
            )

            # 获取凭证
            retrieved = self._vault.get_credential(
                provider="_test",
                credential_type="api_key",
                scope=CredentialScope.API_CALL.value,
            )

            # 删除测试凭证
            self._vault.delete_credential("_test", "api_key")

            return {
                "vault_integrity_verified": retrieved == "test_value_123",
                "test_passed": True,
            }

        except Exception as e:
            return {
                "vault_integrity_verified": False,
                "error": str(e),
            }