"""渐进式上下文压缩核心模块"""

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
from src.context._compressor_utils import build_history_from_session, estimate_tokens
from src.context._config import CompressionConfig, CompressionTier
from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


class ProgressiveContextCompressor:
    """渐进式上下文压缩 - 三层压缩策略"""

    def __init__(self, gateway: "LLMGateway", model_id: str, config: CompressionConfig | None = None):
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or CompressionConfig()

    def compress(self, session: SessionEventStream, context_window: int, system_prompt: str | None = None) -> list[dict[str, Any]]:
        """应用三层压缩"""
        full_history = build_history_from_session(session, system_prompt)
        current_tokens = estimate_tokens(full_history, self._config.token_per_char)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        logger.debug(f"Compressing context: tokens={current_tokens}/{context_window}, usage={usage_ratio:.2%}")

        tier_1_rounds = self._config.tiers[CompressionTier.TIER_1_FULL].keep_rounds
        tier_2_rounds = self._config.tiers[CompressionTier.TIER_2_LIGHT].keep_rounds

        if usage_ratio < self._config.tiers[CompressionTier.TIER_2_LIGHT].threshold:
            compressed = apply_tier_1_only(full_history, tier_1_rounds)
        elif usage_ratio < self._config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold:
            compressed = apply_tier_1_and_2_sync(full_history, tier_1_rounds, tier_2_rounds)
        else:
            compressed = apply_all_tiers_sync(full_history, tier_1_rounds, tier_2_rounds)

        if len(compressed) > self._config.max_context_messages:
            compressed = compressed[-self._config.max_context_messages:]

        logger.info(f"Context compressed: {len(full_history)} -> {len(compressed)} messages")
        return compressed

    async def compress_async(self, session: SessionEventStream, context_window: int, system_prompt: str | None = None) -> list[dict[str, Any]]:
        """异步应用三层压缩"""
        full_history = build_history_from_session(session, system_prompt)
        current_tokens = estimate_tokens(full_history, self._config.token_per_char)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        logger.debug(f"Async compressing context: tokens={current_tokens}/{context_window}, usage={usage_ratio:.2%}")

        tier_1_rounds = self._config.tiers[CompressionTier.TIER_1_FULL].keep_rounds
        tier_2_rounds = self._config.tiers[CompressionTier.TIER_2_LIGHT].keep_rounds

        if usage_ratio < self._config.tiers[CompressionTier.TIER_2_LIGHT].threshold:
            compressed = apply_tier_1_only(full_history, tier_1_rounds)
        elif usage_ratio < self._config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold:
            compressed = await apply_tier_1_and_2_async(full_history, self._gateway, self._model_id, tier_1_rounds, tier_2_rounds)
        else:
            compressed = await apply_all_tiers_async(full_history, self._gateway, self._model_id, tier_1_rounds, tier_2_rounds)

        if len(compressed) > self._config.max_context_messages:
            compressed = compressed[-self._config.max_context_messages:]

        logger.info(f"Context async compressed: {len(full_history)} -> {len(compressed)} messages")
        return compressed