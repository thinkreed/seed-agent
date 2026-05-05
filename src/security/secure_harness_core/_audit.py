"""
审计日志模块

提供凭证访问和请求的审计日志功能：
- get_credential_audit_log: 获取凭证访问日志
- get_request_audit_log: 获取请求审计日志

核心特性：
- 所有凭证访问可追溯
- 请求历史完整记录
- 可配置返回条数限制
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AuditMixin:
    """审计日志功能 Mixin

    提供 get_credential_audit_log 和 get_request_audit_log 方法。
    需要与 SecureHarness 配合使用，依赖 _vault, _credential_proxy 等属性。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        _vault: Any
        _credential_proxy: Any

    def get_credential_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取凭证访问审计日志

        Args:
            limit: 返回条数限制

        Returns:
            审计日志列表
        """
        return self._vault.get_access_audit_log(limit)

    def get_request_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取请求审计日志

        Args:
            limit: 返回条数限制

        Returns:
            请求审计日志列表
        """
        return self._credential_proxy.get_request_audit_log(limit)