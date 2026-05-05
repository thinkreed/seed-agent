"""
统计信息模块

提供安全 Harness 的统计信息功能：
- get_secure_harness_stats: 获取完整统计信息

核心特性：
- Vault 统计
- Proxy 统计
- 外部 API 调用统计
- Sandbox 隔离统计
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StatsMixin:
    """统计信息功能 Mixin

    提供 get_secure_harness_stats 方法。
    需要与 SecureHarness 配合使用，依赖 session, _vault, _credential_proxy, sandbox, _external_api_calls 等属性。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        session: Any
        max_iterations: int
        _vault: Any
        _credential_proxy: Any
        sandbox: Any
        _external_api_calls: int
        _external_api_success: int
        _external_api_failed: int

    def get_secure_harness_stats(self) -> dict[str, Any]:
        """获取安全 Harness 统计信息"""
        from src.security.credential_isolated_sandbox import CredentialIsolatedSandbox

        base_stats = {
            "session_id": self.session.session_id,
            "iterations": self.max_iterations,
            "vault_stats": self._vault.get_vault_stats(),
            "proxy_stats": self._credential_proxy.get_request_stats(),
            "external_api_stats": {
                "total_calls": self._external_api_calls,
                "successful": self._external_api_success,
                "failed": self._external_api_failed,
                "success_rate": (
                    self._external_api_success / self._external_api_calls * 100
                    if self._external_api_calls
                    else 100.0
                ),
            },
        }

        # 如果使用 CredentialIsolatedSandbox，添加隔离统计
        if isinstance(self.sandbox, CredentialIsolatedSandbox):
            base_stats["sandbox_isolation_stats"] = self.sandbox.get_isolation_stats()

        return base_stats