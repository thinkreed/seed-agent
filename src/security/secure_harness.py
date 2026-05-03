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

参考来源: Harness Engineering "凭证永不进沙盒"
"""

import logging
from typing import Any, Callable, TYPE_CHECKING

from src.harness import Harness
from src.security.credential_vault import CredentialVault, CredentialScope
from src.security.credential_proxy import CredentialProxy
from src.security.credential_isolated_sandbox import CredentialIsolatedSandbox

if TYPE_CHECKING:
    from src.llm_client import LLMClient
    from src.session_event_stream import SessionEventStream
    from src.sandbox import Sandbox

logger = logging.getLogger(__name__)


class SecureHarness(Harness):
    """带凭证安全的 Harness

    继承自 Harness，添加凭证安全机制。

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

    # === 外部 API 安全调用 ===

    async def call_external_api(
        self,
        provider: str,
        request_func: Callable[[Any, dict[str, Any]], Any],
        request_context: dict[str, Any],
        requester_id: str | None = None,
        scope: str = CredentialScope.API_CALL.value,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """调用外部 API (通过凭证代理)

        Sandbox 中的代码无法直接访问凭证。
        所有外部请求必须通过此方法执行。

        Args:
            provider: 提供商名称 (如 "openai", "aws", "github")
            request_func: 请求执行函数 (client, context) -> result
            request_context: 请求上下文（不含凭证）
            requester_id: 请求者 ID (用于审计)
            scope: 请求作用域（默认 api_call）
            timeout: 请求超时时间（秒）

        Returns:
            请求结果:
                {"status": "success", "result": ...}
                {"status": "failed", "error": ...}
                {"status": "timeout", "error": ...}

        Example:
            result = await harness.call_external_api(
                provider="openai",
                request_func=lambda client, ctx: client.chat.completions.create(**ctx),
                request_context={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "Hello"}]
                },
                requester_id=session.session_id
            )
        """
        self._external_api_calls += 1

        # 使用默认 requester_id
        if requester_id is None:
            requester_id = self.session.session_id

        result = await self._credential_proxy.execute_external_request(
            provider=provider,
            credential_type="api_key",
            request_func=request_func,
            request_context=request_context,
            requester_id=requester_id,
            scope=scope,
            timeout=timeout,
        )

        # 统计
        if result["status"] == "success":
            self._external_api_success += 1
        else:
            self._external_api_failed += 1

        return result

    async def call_llm_with_credential_proxy(
        self,
        messages: list[dict[str, Any]],
        model_id: str | None = None,
        requester_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """调用 LLM (通过凭证代理)

        凭证不暴露给 Sandbox，通过代理安全调用。

        Args:
            messages: 消息列表
            model_id: 模型 ID（可选，默认使用 llm_client 的 model_id）
            requester_id: 请求者 ID
            **kwargs: 其他 LLM 参数

        Returns:
            LLM 响应结果
        """
        provider = model_id.split("/")[0] if model_id else self.llm_client.model_id.split("/")[0]

        # 通过代理调用 LLM
        async def llm_request_func(client, context):
            return await client.chat.completions.create(**context)

        request_context = {
            "model": model_id or self.llm_client.model_id.split("/")[-1],
            "messages": messages,
            **kwargs,
        }

        return await self.call_external_api(
            provider=provider,
            request_func=llm_request_func,
            request_context=request_context,
            requester_id=requester_id,
        )

    # === 凭证管理 ===

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

    # === 审计日志 ===

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

    # === 统计信息 ===

    def get_secure_harness_stats(self) -> dict[str, Any]:
        """获取安全 Harness 统计信息"""
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
                    if self._external_api_calls else 100.0
                ),
            },
        }

        # 如果使用 CredentialIsolatedSandbox，添加隔离统计
        if isinstance(self.sandbox, CredentialIsolatedSandbox):
            base_stats["sandbox_isolation_stats"] = self.sandbox.get_isolation_stats()

        return base_stats

    # === 工具执行覆盖 ===

    async def _route_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """路由工具调用到 Sandbox（带凭证安全检查）

        如果使用 CredentialIsolatedSandbox，自动使用隔离执行。

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具执行结果列表
        """
        # 如果使用 CredentialIsolatedSandbox，使用隔离执行
        if isinstance(self.sandbox, CredentialIsolatedSandbox):
            secure_results = await self.sandbox.execute_tools_isolated(tool_calls)

            # 转换为标准格式
            return [
                {
                    "tool_call_id": result.tool_call_id,
                    "role": "tool",
                    "content": result.content,
                }
                for result in secure_results
            ]

        # 默认使用标准 Harness 执行
        return await super()._route_tool_calls(tool_calls)

    # === 验证方法 ===

    async def verify_credential_isolation(self) -> dict[str, Any]:
        """验证凭证隔离是否有效

        Returns:
            验证结果
        """
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