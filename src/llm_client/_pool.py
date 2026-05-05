"""LLMClientPool 模块

LLMClientPool: 客户端池 - 支持多模型实例

用于管理多个 LLMClient 实例，支持：
- 多模型并行推理
- 模型故障转移
- 负载均衡
"""

import logging
from typing import Any

from src.client import LLMGateway
from src.request_queue import RequestPriority

from ._client import LLMClient

logger = logging.getLogger(__name__)


class LLMClientPool:
    """LLM 客户端池 - 支持多模型实例

    用于管理多个 LLMClient 实例，支持：
    - 多模型并行推理
    - 模型故障转移
    - 负载均衡

    使用场景：
    - 多模型协作
    - 故障转移
    - A/B 测试
    """

    def __init__(self, gateway: LLMGateway):
        """初始化 LLMClientPool

        Args:
            gateway: LLM Gateway 实例
        """
        self._gateway = gateway
        self._clients: dict[str, LLMClient] = {}
        self._primary_model: str | None = None

        logger.info("LLMClientPool initialized")

    def add_client(
        self,
        model_id: str,
        is_primary: bool = False,
        priority: int = RequestPriority.NORMAL,
    ) -> LLMClient:
        """添加 LLM 客户端

        Args:
            model_id: 模型 ID
            is_primary: 是否为主模型
            priority: 默认优先级

        Returns:
            LLMClient 实例
        """
        client = LLMClient(self._gateway, model_id, priority)
        self._clients[model_id] = client

        if is_primary:
            self._primary_model = model_id

        logger.info(f"LLMClient added: model={model_id}, primary={is_primary}")
        return client

    def get_client(self, model_id: str | None = None) -> LLMClient:
        """获取 LLM 客户端

        Args:
            model_id: 模型 ID，如不指定则使用主模型

        Returns:
            LLMClient 实例
        """
        if model_id:
            if model_id not in self._clients:
                raise ValueError(f"Model not in pool: {model_id}")
            return self._clients[model_id]

        if not self._primary_model:
            raise ValueError("No primary model set")

        return self._clients[self._primary_model]

    def get_primary_client(self) -> LLMClient:
        """获取主模型客户端"""
        if not self._primary_model:
            raise ValueError("No primary model set")
        return self._clients[self._primary_model]

    def list_models(self) -> list[str]:
        """列出所有模型"""
        return list(self._clients.keys())

    def remove_client(self, model_id: str) -> bool:
        """移除客户端"""
        if model_id in self._clients:
            del self._clients[model_id]
            if self._primary_model == model_id:
                self._primary_model = next(iter(self._clients.keys()), None)
            logger.info(f"LLMClient removed: model={model_id}")
            return True
        return False

    async def reason_with_fallback(
        self,
        context: list[dict[str, Any]],
        tools: list[dict] | None = None,
        priority: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict[str, Any]:
        """带故障转移的推理

        Args:
            context: 上下文消息
            tools: 工具 schema
            priority: 优先级
            fallback_models: 故障转移模型列表

        Returns:
            推理结果
        """
        models_to_try = [self._primary_model] if self._primary_model else []
        if fallback_models:
            models_to_try.extend(fallback_models)

        for model_id in models_to_try:
            if model_id not in self._clients:
                continue

            try:
                client = self._clients[model_id]
                return await client.reason(context, tools, priority)
            except Exception as e:
                logger.warning(f"Model {model_id} failed: {type(e).__name__}: {e}")
                continue

        raise RuntimeError("All models failed, no fallback available")

    def get_pool_status(self) -> dict[str, Any]:
        """获取池状态"""
        return {
            "models": list(self._clients.keys()),
            "primary_model": self._primary_model,
            "clients_count": len(self._clients),
        }