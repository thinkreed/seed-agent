"""
LLMClient (大脑) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- LLMClient 是大脑，负责推理
- 本身无状态，只接收上下文并返回推理结果
- 可配置多个模型实例，支持多模型切换
- 从 AgentLoop 中解耦，降低首 Token 延迟

核心职责：
1. 封装 LLM Gateway 的推理调用
2. 提供统一的推理 API (普通/流式)
3. 处理模型配置获取
4. 不持有任何对话状态

使用方式：
    llm = LLMClient(gateway, "qwen/qwen-coder-plus")
    response = await llm.reason(context_messages, tools=tool_schemas)
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.client import LLMGateway
from src.request_queue import RequestPriority

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 大脑 - 负责推理，无状态

    三件套解耦架构中的"大脑"层：
    - 接收上下文 messages (从 Session 构建)
    - 调用 LLM Gateway 执行推理
    - 返回推理结果 (响应 + 可能的 tool_calls)
    - 不持有任何状态

    性能优化：
    - 大脑与容器(Sandbox)分离
    - 首 Token 延迟降低 60-90%
    """

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str,
        default_priority: int = RequestPriority.NORMAL
    ):
        """初始化 LLMClient

        Args:
            gateway: LLM Gateway 实例
            model_id: 模型 ID (格式: provider/model)
            default_priority: 默认请求优先级
        """
        self.gateway = gateway
        self.model_id = model_id
        self.default_priority = default_priority

        # 缓存模型配置（避免重复查询）
        self._model_config = gateway.get_model_config(model_id)

        logger.info(
            f"LLMClient initialized: model={model_id}, "
            f"context_window={self._model_config.contextWindow}"
        )

    async def reason(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        **kwargs
    ) -> dict[str, Any]:
        """执行推理

        Args:
            context: 上下文消息列表 (从 Session 构建)
            tools: 可用工具 schema 列表
            priority: 请求优先级 (默认使用 default_priority)
            **kwargs: 其他 LLM 参数

        Returns:
            推理结果 dict，包含:
            - choices: 响应选择列表
            - usage: Token 使用统计
            - model: 使用的模型 ID
        """
        if priority is None:
            priority = self.default_priority

        logger.debug(
            f"LLMClient.reason: model={self.model_id}, "
            f"context_len={len(context)}, tools={len(tools) if tools else 0}"
        )

        response = await self.gateway.chat_completion(
            self.model_id,
            context,
            priority=priority,
            tools=tools,
            **kwargs
        )

        return response

    async def stream_reason(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式推理

        Args:
            context: 上下文消息列表
            tools: 可用工具 schema
            priority: 请求优先级
            **kwargs: 其他 LLM 参数

        Yields:
            流式响应 chunk
        """
        if priority is None:
            priority = self.default_priority

        logger.debug(
            f"LLMClient.stream_reason: model={self.model_id}, "
            f"context_len={len(context)}, tools={len(tools) if tools else 0}"
        )

        async for chunk in self.gateway.stream_chat_completion(
            self.model_id,
            context,
            priority=priority,
            tools=tools,
            **kwargs
        ):
            yield chunk

    def get_context_window(self) -> int:
        """获取模型上下文窗口大小"""
        return self._model_config.contextWindow

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        return {
            "model_id": self.model_id,
            "context_window": self._model_config.contextWindow,
            "max_output_tokens": getattr(
                self._model_config, "maxOutputTokens", 4096
            ),
            "provider": self.model_id.split("/", 1)[0] if "/" in self.model_id else "unknown"
        }

    async def get_active_provider(self) -> str:
        """获取当前活跃的 Provider（通过 Gateway）"""
        return await self.gateway.get_active_provider()