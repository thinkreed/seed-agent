"""TTRL 记忆整合器

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning

核心功能：
- 记忆整合与去重
"""

import logging
from pathlib import Path

from ._memory_write import VerifiedSource, write_memory
from ._ttrl_types import (
    ConsolidationResult,
    JudgementType,
    MemoryEntry,
    MemorySource,
)

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """记忆整合器

    MIA 记忆整合逻辑：
    - 相似度 ≥ threshold 时执行去重
    - 现有记忆错误 + 新记忆正确 → 替换
    - 都正确 → 保留更短版本
    - 更新 win_rate 统计
    """

    def __init__(self, memory_root: Path) -> None:
        """初始化

        Args:
            memory_root: 记忆根目录
        """
        self._memory_root = memory_root
        self._memory_buffer: list[MemoryEntry] = []

    def add_memory_entry(self, entry: MemoryEntry) -> None:
        """添加记忆条目到缓冲区

        Args:
            entry: 记忆条目
        """
        self._memory_buffer.append(entry)

    def consolidate_memories(
        self,
        similarity_threshold: float = 0.9999,
    ) -> ConsolidationResult:
        """整合记忆

        Args:
            similarity_threshold: 相似度阈值

        Returns:
            整合结果
        """
        result = ConsolidationResult(
            total_traces=len(self._memory_buffer),
            correct_count=0,
            incorrect_count=0,
            new_memories=0,
            updated_memories=0,
            skipped_memories=0,
        )

        for entry in self._memory_buffer:
            # 统计正确/错误
            if entry.judgement == JudgementType.CORRECT:
                result.correct_count += 1
            elif entry.judgement == JudgementType.INCORRECT:
                result.incorrect_count += 1

            # 尝试写入记忆
            write_result = self._write_memory_with_dedup(entry, similarity_threshold)

            if write_result.startswith("Saved"):
                result.new_memories += 1
            elif write_result.startswith("Updated"):
                result.updated_memories += 1
            elif write_result.startswith("Skipped"):
                result.skipped_memories += 1
            else:
                result.errors.append(write_result)

        # 清空缓冲区
        self._memory_buffer.clear()

        return result

    def _write_memory_with_dedup(
        self,
        entry: MemoryEntry,
        threshold: float,
    ) -> str:
        """写入记忆（带去重逻辑）

        Args:
            entry: 记忆条目
            threshold: 相似度阈值

        Returns:
            写入结果描述
        """
        # 映射 MemorySource 到 VerifiedSource
        source_mapping = {
            MemorySource.EXECUTOR: VerifiedSource.TOOL_CALL_SUCCESS,
            MemorySource.PLANNER: VerifiedSource.TOOL_CALL_SUCCESS,
            MemorySource.TOOL_CALL: VerifiedSource.TOOL_CALL_SUCCESS,
            MemorySource.USER_FEEDBACK: VerifiedSource.EXTERNAL_VERIFICATION,
        }

        verified_source = source_mapping.get(entry.source, VerifiedSource.UNVERIFIED)

        # 构建内容
        content = entry.workflow_summary
        if entry.plan:
            content = f"## Workflow\n{entry.workflow_summary}\n\n## Plan\n{entry.plan}"

        metadata = f"win_rate={entry.win_rate}, usage={entry.usage_count}, source={entry.source.value}"

        # 写入记忆（L3 知识层）
        return write_memory(
            level="L3",
            content=content,
            title=f"ttrl_{entry.data_id or entry.question[:30]}",
            metadata=metadata,
            source=verified_source,
            similarity_threshold=threshold,
        )

    @property
    def memory_root(self) -> Path:
        """记忆根目录"""
        return self._memory_root

    def clear(self) -> None:
        """清空缓冲区"""
        self._memory_buffer.clear()


__all__ = ["MemoryConsolidator"]