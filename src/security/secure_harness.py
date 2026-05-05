"""
安全 Harness - SecureHarness

基于 Harness Engineering "凭证永不进沙盒" 设计理念：
- 继承 Harness，添加凭证安全支持
- 通过 CredentialProxy 调用外部 API
- Sandbox 中的代码无法直接访问凭证
- 所有外部调用可审计

核心特性:
- 凭证代理集成
- 外部 API 调用安全封装
- LLM 调用凭证隔离
- 完整审计日志

模块拆分:
- secure_harness_core/_api_calls.py: 外部 API 安全调用
- secure_harness_core/_audit.py: 审计日志
- secure_harness_core/_stats.py: 统计信息
- secure_harness_core/_verification.py: 验证方法
- secure_harness_core/_credential_management.py: 凭证管理
- secure_harness_core/_tool_routing.py: 工具路由

参考来源: Harness Engineering "凭证永不进沙盒"
"""

import logging
from typing import TYPE_CHECKING

from src.harness import Harness
from src.security.credential_isolated_sandbox import CredentialIsolatedSandbox
from src.security.credential_proxy import CredentialProxy
from src.security.credential_vault import CredentialVault
from src.security.secure_harness_core import (
    ApiCallsMixin,
    AuditMixin,
    CredentialManagementMixin,
    StatsMixin,
    ToolRoutingMixin,
    VerificationMixin,
)

if TYPE_CHECKING:
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


class SecureHarness(
    ApiCallsMixin,
    AuditMixin,
    CredentialManagementMixin,
    StatsMixin,
    ToolRoutingMixin,
    VerificationMixin,
    Harness,
):
    """带凭证安全的 Harness

    继承自 Harness，添加凭证安全机制。
    使用 Mixin 组合拆分后的功能模块。

    核心特性:
    - 凭证代理集成：所有外部请求通过 CredentialProxy
    - Sandbox 凭证隔离：使用 CredentialIsolatedSandbox
    - 外部 API 安全调用：凭证不暴露给执行代码
    - 完整审计：所有凭证访问可追溯

    Example:
        vault = CredentialVault()
        vault.store_credential("openai", "api_key", "sk-test123")

        proxy = CredentialProxy(vault)
        sandbox = CredentialIsolatedSandbox(credential_proxy=proxy)

        harness = SecureHarness(
            llm_client=client,
            session=session,
            sandbox=sandbox,
            vault=vault,
            credential_proxy=proxy
        )

        # 外部 API 调用通过代理（凭证不暴露）
        result = await harness.call_external_api(
            provider="openai",
            request_func=lambda client, ctx: client.chat.completions.create(**ctx),
            request_context={"model": "gpt-4", "messages": [...]}
        )
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        session: "SessionEventStream",
        sandbox: "Sandbox",
        vault: CredentialVault,
        credential_proxy: CredentialProxy,
        max_iterations: int = 30,
        system_prompt: str | None = None,
        **kwargs,
    ):
        """初始化安全 Harness

        Args:
            llm_client: LLMClient (大脑)
            session: SessionEventStream (状态存储)
            sandbox: Sandbox (执行环境，推荐使用 CredentialIsolatedSandbox)
            vault: CredentialVault (凭证保险库)
            credential_proxy: CredentialProxy (凭证代理)
            max_iterations: 最大迭代次数
            system_prompt: 系统提示
            **kwargs: 其他 Harness 参数
        """
        super().__init__(
            llm_client=llm_client,
            session=session,
            sandbox=sandbox,
            max_iterations=max_iterations,
            system_prompt=system_prompt,
            **kwargs,
        )

        # 凭证安全组件
        self._vault = vault
        self._credential_proxy = credential_proxy

        # 外部调用统计
        self._external_api_calls = 0
        self._external_api_success = 0
        self._external_api_failed = 0

        logger.info(
            f"SecureHarness initialized: "
            f"session={session.session_id}, "
            f"vault_enabled=True, "
            f"sandbox_type={type(sandbox).__name__}"
        )


__all__ = ["SecureHarness"]