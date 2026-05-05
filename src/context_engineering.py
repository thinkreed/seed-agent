"""
上下文工程模块（主入口）

基于 Harness Engineering "上下文工程" 设计：
- 渐进式压缩：最新完整保留 → 稍旧轻量总结 → 更早简短摘要
- 智能裁剪：根据任务相关性过滤不相关历史
- 原始数据不丢失：Session 保留完整历史

此文件作为公共 API 入口，具体实现拆分到子模块：
- src/context/_config.py: 配置类
- src/context/_compressor.py: ProgressiveContextCompressor
- src/context/_pruner.py: IntelligentContextPruner

公共 API 导出（保持向后兼容）：
- CompressionConfig, CompressionTier, TierConfig: 压缩配置
- PruningConfig: 裁剪配置
- ProgressiveContextCompressor: 渐进式压缩器
- IntelligentContextPruner: 智能裁剪器
- ContextEngineering: 集成管理器
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.session_event_stream import SessionEventStream

# 从子模块导入核心类
from src.context._config import (
    CompressionConfig,
    CompressionTier,
    PruningConfig,
)
from src.context._compressor import ProgressiveContextCompressor
from src.context._pruner import IntelligentContextPruner

logger = logging.getLogger(__name__)


class ContextEngineering:
    """上下文工程集成管理器

    协调渐进式压缩和智能裁剪：
    - 先裁剪（基于任务相关性）
    - 后压缩（基于容量使用率）

    使用流程:
    1. 创建实例，传入 Gateway 和 Session
    2. 调用 build_optimized_context() 获取优化后的上下文
    3. 发送给 LLM 推理
    """

    def __init__(
        self,
        gateway: "LLMGateway",
        model_id: str,
        compression_config: CompressionConfig | None = None,
        pruning_config: PruningConfig | None = None,
    ):
        """初始化上下文工程管理器

        Args:
            gateway: LLM Gateway 实例
            model_id: 模型 ID
            compression_config: 压缩配置
            pruning_config: 裁剪配置
        """
        self._gateway = gateway
        self._model_id = model_id

        self._compressor = ProgressiveContextCompressor(
            gateway, model_id, compression_config
        )
        self._pruner = IntelligentContextPruner(gateway, model_id, pruning_config)

        logger.info(f"ContextEngineering initialized: model={model_id}")

    def build_optimized_context(
        self,
        session: SessionEventStream,
        context_window: int,
        current_task: str | None = None,
        system_prompt: str | None = None,
        enable_pruning: bool = True,
    ) -> list[dict[str, Any]]:
        """构建优化后的上下文（同步版本）

        流程：
        1. 从 Session 构建完整历史
        2. 智能裁剪（可选，基于任务相关性）
        3. 渐进式压缩（基于容量使用率）

        Args:
            session: 事件流
            context_window: 上下文窗口大小
            current_task: 当前任务描述（用于裁剪）
            system_prompt: 系统提示
            enable_pruning: 是否启用裁剪

        Returns:
            优化后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._compressor._build_history_from_session(
            session, system_prompt
        )

        # 2. 智能裁剪（可选）
        if enable_pruning and current_task:
            pruned_history = self._pruner.prune_for_task(full_history, current_task)
        else:
            pruned_history = full_history

        # 3. 渐进式压缩
        # 注意：压缩器需要重新从 session 构建，因为裁剪可能改变了结构
        # 这里我们直接对 pruned_history 应用压缩策略
        compressed = self._apply_compression_to_pruned(
            pruned_history, context_window, system_prompt
        )

        logger.info(
            f"Context optimized: full={len(full_history)}, "
            f"pruned={len(pruned_history)}, final={len(compressed)}"
        )

        return compressed

    async def build_optimized_context_async(
        self,
        session: SessionEventStream,
        context_window: int,
        current_task: str | None = None,
        system_prompt: str | None = None,
        enable_pruning: bool = True,
        enable_semantic_pruning: bool = False,
    ) -> list[dict[str, Any]]:
        """构建优化后的上下文（异步版本，支持 LLM 摘要）

        Args:
            session: 事件流
            context_window: 上下文窗口大小
            current_task: 当前任务描述
            system_prompt: 系统提示
            enable_pruning: 是否启用裁剪
            enable_semantic_pruning: 是否启用语义裁剪（LLM）

        Returns:
            优化后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._compressor._build_history_from_session(
            session, system_prompt
        )

        # 2. 智能裁剪（可选）
        if enable_pruning and current_task:
            if enable_semantic_pruning:
                pruned_history = await self._pruner.prune_with_semantic_relevance(
                    full_history, current_task
                )
            else:
                pruned_history = self._pruner.prune_for_task(full_history, current_task)
        else:
            pruned_history = full_history

        # 3. 渐进式压缩（异步，支持 LLM 摘要）
        return await self._apply_compression_to_pruned_async(
            pruned_history, context_window, system_prompt
        )

    def _apply_compression_to_pruned(
        self,
        pruned_history: list[dict[str, Any]],
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """对已裁剪的历史应用压缩（同步）"""
        # 估算 Token
        current_tokens = self._compressor._estimate_tokens(pruned_history)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        # 根据使用率选择压缩层级
        config = self._compressor._config
        tier_2_threshold = config.tiers[CompressionTier.TIER_2_LIGHT].threshold
        tier_3_threshold = config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold

        if usage_ratio < tier_2_threshold:
            return self._compressor._apply_tier_1_only(pruned_history)
        if usage_ratio < tier_3_threshold:
            return self._compressor._apply_tier_1_and_2(pruned_history)
        return self._compressor._apply_all_tiers(pruned_history)

    async def _apply_compression_to_pruned_async(
        self,
        pruned_history: list[dict[str, Any]],
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """对已裁剪的历史应用压缩（异步）"""
        current_tokens = self._compressor._estimate_tokens(pruned_history)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        config = self._compressor._config
        tier_2_threshold = config.tiers[CompressionTier.TIER_2_LIGHT].threshold
        tier_3_threshold = config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold

        if usage_ratio < tier_2_threshold:
            return self._compressor._apply_tier_1_only(pruned_history)
        if usage_ratio < tier_3_threshold:
            return await self._compressor._apply_tier_1_and_2_async(pruned_history)
        return await self._compressor._apply_all_tiers_async(pruned_history)

    def get_compressor(self) -> ProgressiveContextCompressor:
        """获取压缩器实例"""
        return self._compressor

    def get_pruner(self) -> IntelligentContextPruner:
        """获取裁剪器实例"""
        return self._pruner


# 重新导出子模块的公共类（保持向后兼容）
# 用户可以从 context_engineering 或 context 包导入
__all__ = [
    # 配置类
    "CompressionConfig",
    "CompressionTier",
    "TierConfig",
    "PruningConfig",
    # 核心类
    "ProgressiveContextCompressor",
    "IntelligentContextPruner",
    # 集成管理器
    "ContextEngineering",
]

# 从子模块导入 TierConfig 以便导出
from src.context._config import TierConfig