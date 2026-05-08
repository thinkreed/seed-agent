"""TTRL 处理器核心逻辑

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning

核心功能：
- 执行轨迹评估
- 记忆整合
- Win Rate 统计

重构说明：
- 执行轨迹处理委托给 TraceEvaluator
- 记忆整合委托给 MemoryConsolidator
- Win Rate 统计委托给 _ttrl_stats.get_win_rate_stats
"""

import logging
from pathlib import Path

from ._ttrl_memory_consolidator import MemoryConsolidator
from ._ttrl_stats import get_win_rate_stats
from ._ttrl_trace_evaluator import TraceEvaluator
from ._ttrl_types import (
    ConsolidationResult,
    ExecutionTrace,
    MemoryEntry,
)

logger = logging.getLogger(__name__)


class TTRLProcessor:
    """TTRL 处理器

    实现推理时持续学习：
    - 执行轨迹评估
    - 记忆整合
    - Win Rate 统计
    """

    def __init__(self, memory_root: Path | None = None):
        """初始化

        Args:
            memory_root: 记忆根目录
        """
        self._memory_root = memory_root or self._get_memory_root()
        self._trace_evaluator = TraceEvaluator()
        self._memory_consolidator = MemoryConsolidator(self._memory_root)

    def _get_memory_root(self) -> Path:
        """获取记忆根目录"""
        try:
            from src.shared_config import get_paths_config

            return get_paths_config().memory_dir
        except RuntimeError:
            return Path.home() / ".seed" / "memory"

    # ========================================================================
    # 执行轨迹处理（委托给 TraceEvaluator）
    # ========================================================================

    def add_trace(self, trace: ExecutionTrace) -> None:
        """添加执行轨迹到缓冲区"""
        self._trace_evaluator.add_trace(trace)

    def batch_evaluate(self) -> dict[str, object]:
        """批量评估执行轨迹"""
        return self._trace_evaluator.batch_evaluate()

    # ========================================================================
    # 记忆整合（委托给 MemoryConsolidator）
    # ========================================================================

    def add_memory_entry(self, entry: MemoryEntry) -> None:
        """添加记忆条目到缓冲区"""
        self._memory_consolidator.add_memory_entry(entry)

    def consolidate_memories(
        self,
        similarity_threshold: float = 0.9999,
    ) -> ConsolidationResult:
        """整合记忆

        MIA 记忆整合逻辑：
        - 相似度 ≥ threshold 时执行去重
        - 现有记忆错误 + 新记忆正确 → 替换
        - 都正确 → 保留更短版本
        - 更新 win_rate 统计

        Args:
            similarity_threshold: 相似度阈值

        Returns:
            整合结果
        """
        result = self._memory_consolidator.consolidate_memories(similarity_threshold)

        # 同时清空轨迹缓冲区
        self._trace_evaluator.clear()

        return result

    # ========================================================================
    # Win Rate 统计（委托给 get_win_rate_stats）
    # ========================================================================

    def get_win_rate_stats(self, memory_dir: Path | None = None) -> dict[str, object]:
        """获取 Win Rate 统计

        分析已存储记忆的胜率分布。

        Args:
            memory_dir: 记忆目录（默认 L3 knowledge）

        Returns:
            统计结果
        """
        target_dir = memory_dir or (self._memory_consolidator.memory_root / "knowledge")
        return get_win_rate_stats(target_dir)


__all__ = ["TTRLProcessor"]