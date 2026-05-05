"""
渐进式上下文压缩核心模块

整合压缩层级、工具函数，提供统一的压缩接口
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.context._compressor_tiers import (
    apply_all_tiers_async,
    apply_all_tiers_sync,
    apply_tier_1_and_2_async,
    apply_tier_1_and_2_sync,
    apply_tier_1_only,
)
from src.context._compressor_utils import (
    build_history_from_session,
    estimate_tokens,
)
from src.context._config import CompressionConfig, CompressionTier
from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


class ProgressiveContextCompressor:
    """渐进式上下文压缩

    三层压缩策略：
    - Tier 1: 最新 5 轮完整保留 (Full)
    - Tier 2: 稍旧 10 轮轻量总结 (Light Summary) - 50% 容量时触发
    - Tier 3: 更早历史简短摘要 (Abstract) - 75% 容量时触发

    核心特性：
    - 渐进信息损失，不丢失原始数据（Session 保留）
    - 根据上下文使用率动态选择压缩层级
    """

    def __init__(
        self,
        gateway: "LLMGateway",
        model_id: str,
        config: CompressionConfig | None = None,
    ):
        """初始化压缩器

        Args:
            gateway: LLM Gateway 实例（用于生成摘要）
            model_id: 模型 ID
            config: 压缩配置
        """
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or CompressionConfig()

    def compress(
        self,
        session: SessionEventStream,
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """应用三层压缩

        Args:
            session: 事件流（原始数据不丢失）
            context_window: 上下文窗口大小
            system_prompt: 系统提示

        Returns:
            压缩后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = build_history_from_session(session, system_prompt)

        # 2. 计算当前容量使用率
        current_tokens = estimate_tokens(full_history, self._config.token_per_char)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        logger.debug(
            f"Compressing context: tokens={current_tokens}/{context_window}, "
            f"usage={usage_ratio:.2%}"
        )

        # 3. 获取配置参数
        tier_1_rounds = self._config.tiers[CompressionTier.TIER_1_FULL].keep_rounds
        tier_2_rounds = self._config.tiers[CompressionTier.TIER_2_LIGHT].keep_rounds

        # 4. 根据使用率决定压缩层级
        if usage_ratio < self._config.tiers[CompressionTier.TIER_2_LIGHT].threshold:
            # 低使用率：Tier 1 仅
            compressed = apply_tier_1_only(full_history, tier_1_rounds)
        elif (
            usage_ratio < self._config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold
        ):
            # 中使用率：Tier 1 + Tier 2
            compressed = apply_tier_1_and_2_sync(
                full_history, tier_1_rounds, tier_2_rounds
            )
        else:
            # 高使用率：完整三层
            compressed = apply_all_tiers_sync(
                full_history, tier_1_rounds, tier_2_rounds
            )

        # 5. 应用消息数量限制
        if len(compressed) > self._config.max_context_messages:
            compressed = compressed[-self._config.max_context_messages :]

        logger.info(
            f"Context compressed: {len(full_history)} -> {len(compressed)} messages, "
            f"usage={usage_ratio:.2%}"
        )

        return compressed

    async def compress_async(
        self,
        session: SessionEventStream,
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """异步应用三层压缩（使用 LLM 生成摘要）

        Args:
            session: 事件流
            context_window: 上下文窗口大小
            system_prompt: 系统提示

        Returns:
            压缩后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = build_history_from_session(session, system_prompt)

        # 2. 计算当前容量使用率
        current_tokens = estimate_tokens(full_history, self._config.token_per_char)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        logger.debug(
            f"Async compressing context: tokens={current_tokens}/{context_window}, "
            f"usage={usage_ratio:.2%}"
        )

        # 3. 获取配置参数
        tier_1_rounds = self._config.tiers[CompressionTier.TIER_1_FULL].keep_rounds
        tier_2_rounds = self._config.tiers[CompressionTier.TIER_2_LIGHT].keep_rounds

        # 4. 根据使用率决定压缩层级
        if usage_ratio < self._config.tiers[CompressionTier.TIER_2_LIGHT].threshold:
            compressed = apply_tier_1_only(full_history, tier_1_rounds)
        elif (
            usage_ratio < self._config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold
        ):
            compressed = await apply_tier_1_and_2_async(
                full_history, self._gateway, self._model_id, tier_1_rounds, tier_2_rounds
            )
        else:
            compressed = await apply_all_tiers_async(
                full_history, self._gateway, self._model_id, tier_1_rounds, tier_2_rounds
            )

        # 5. 应用消息数量限制
        if len(compressed) > self._config.max_context_messages:
            compressed = compressed[-self._config.max_context_messages :]

        logger.info(
            f"Context async compressed: {len(full_history)} -> {len(compressed)} messages"
        )

        return compressed