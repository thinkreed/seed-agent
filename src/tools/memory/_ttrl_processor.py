"""TTRL 处理器核心逻辑

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning

核心功能：
- 执行轨迹评估
- 记忆整合
- Win Rate 统计
"""

import logging
import re
from pathlib import Path

from ._ttrl_types import (
    ConsolidationResult,
    ExecutionTrace,
    JudgementType,
    MemoryEntry,
    MemorySource,
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
        self._trace_buffer: list[ExecutionTrace] = []
        self._memory_buffer: list[MemoryEntry] = []

    def _get_memory_root(self) -> Path:
        """获取记忆根目录"""
        try:
            from src.shared_config import get_paths_config
            return get_paths_config().memory_dir
        except RuntimeError:
            return Path.home() / ".seed" / "memory"

    # ========================================================================
    # 执行轨迹处理
    # ========================================================================

    def add_trace(self, trace: ExecutionTrace) -> None:
        """添加执行轨迹到缓冲区"""
        self._trace_buffer.append(trace)

    def batch_evaluate(self) -> dict[str, object]:
        """批量评估执行轨迹

        分析轨迹中的成功/失败指标，生成 reward 信号。

        Returns:
            评估结果统计
        """
        results = {
            "total": len(self._trace_buffer),
            "correct": 0,
            "incorrect": 0,
            "partial": 0,
            "unknown": 0,
            "avg_duration_ms": 0.0,
            "tools_usage": {},
        }

        if not self._trace_buffer:
            return results

        total_duration = 0.0
        tools_usage: dict[str, int] = {}

        for trace in self._trace_buffer:
            # 统计判断类型
            if trace.judgement == JudgementType.CORRECT:
                results["correct"] += 1
            elif trace.judgement == JudgementType.INCORRECT:
                results["incorrect"] += 1
            elif trace.judgement == JudgementType.PARTIAL:
                results["partial"] += 1
            else:
                results["unknown"] += 1

            # 统计工具使用
            for tool in trace.tools_used:
                tools_usage[tool] = tools_usage.get(tool, 0) + 1

            # 累计时长
            total_duration += trace.duration_ms

        results["avg_duration_ms"] = total_duration / len(self._trace_buffer)
        results["tools_usage"] = tools_usage

        return results

    # ========================================================================
    # 记忆整合
    # ========================================================================

    def add_memory_entry(self, entry: MemoryEntry) -> None:
        """添加记忆条目到缓冲区"""
        self._memory_buffer.append(entry)

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
        self._trace_buffer.clear()

        return result

    def _write_memory_with_dedup(
        self,
        entry: MemoryEntry,
        threshold: float,
    ) -> str:
        """写入记忆（带去重逻辑）"""
        from ._memory_write import (
            VerifiedSource,
            write_memory,
        )

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
        )

    # ========================================================================
    # Win Rate 统计
    # ========================================================================

    def get_win_rate_stats(self, memory_dir: Path | None = None) -> dict[str, object]:
        """获取 Win Rate 统计

        分析已存储记忆的胜率分布。

        Args:
            memory_dir: 记忆目录（默认 L3 knowledge）

        Returns:
            统计结果
        """
        stats = {
            "total_memories": 0,
            "avg_win_rate": 0.0,
            "high_win_rate": [],  # win_rate >= 0.8
            "low_win_rate": [],  # win_rate < 0.5
            "usage_distribution": {},
        }

        target_dir = memory_dir or (self._memory_root / "knowledge")
        if not target_dir.exists():
            return stats

        win_rates = []
        usage_counts: dict[int, int] = {}

        for file in target_dir.glob("*.md"):
            try:
                with open(file, encoding="utf-8") as f:
                    content = f.read()

                # 解析 metadata
                if "win_rate=" in content:
                    match = re.search(r"win_rate=(\d+\.?\d*)", content)
                    if match:
                        win_rate = float(match.group(1))
                        win_rates.append(win_rate)
                        stats["total_memories"] += 1

                        # 分类
                        if win_rate >= 0.8:
                            stats["high_win_rate"].append(file.name)
                        elif win_rate < 0.5:
                            stats["low_win_rate"].append(file.name)

                # 解析 usage_count
                if "usage=" in content:
                    match = re.search(r"usage=(\d+)", content)
                    if match:
                        usage = int(match.group(1))
                        usage_counts[usage] = usage_counts.get(usage, 0) + 1

            except Exception:
                continue

        if win_rates:
            stats["avg_win_rate"] = sum(win_rates) / len(win_rates)

        stats["usage_distribution"] = usage_counts

        return stats


__all__ = ["TTRLProcessor"]