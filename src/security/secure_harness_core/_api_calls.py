"""
外部 API 安全调用模块

提供通过 CredentialProxy 的外部 API 调用功能：
- call_external_api: 安全调用外部 API
- call_llm_with_credential_proxy: 通过代理调用 LLM

核心特性：
- 凭证不暴露给 Sandbox
- 所有请求可审计
- 调用统计追踪
"""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ApiCallsMixin:
    """外部 API 调用功能 Mixin

    提供 call_external_api 和 call_llm_with_credential_proxy 方法。
    需要与 SecureHarness 配合使用，依赖 _credential_proxy, session, llm_client 等属性。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        _credential_proxy: Any
        session: Any
        llm_client: Any
        _external_api_calls: int
        _external_api_success: int
        _external_api_failed: int

    async def call_external_api(
        self,
        provider: str,
        request_func: Callable[[Any, dict[str, Any]], Any],
        request_context: dict[str, Any],
        requester_id: str | None = None,
        scope: str = "api_call",
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
        provider = (
            model_id.split("/")[0]
            if model_id
            else self.llm_client.model_id.split("/")[0]
        )

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