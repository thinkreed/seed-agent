"""TTRL 执行轨迹评估器

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning

核心功能：
- 执行轨迹缓冲
- 批量评估
- 工具使用统计
"""

import logging

from ._ttrl_types import ExecutionTrace, JudgementType

logger = logging.getLogger(__name__)


class TraceEvaluator:
    """执行轨迹评估器

    分析轨迹中的成功/失败指标，生成 reward 信号。
    """

    def __init__(self) -> None:
        """初始化评估器"""
        self._trace_buffer: list[ExecutionTrace] = []

    def add_trace(self, trace: ExecutionTrace) -> None:
        """添加执行轨迹到缓冲区

        Args:
            trace: 执行轨迹
        """
        self._trace_buffer.append(trace)

    def batch_evaluate(self) -> dict[str, object]:
        """批量评估执行轨迹

        分析轨迹中的成功/失败指标，生成 reward 信号。

        Returns:
            评估结果统计，包含：
            - total: 总数
            - correct/incorrect/partial/unknown: 判断类型计数
            - avg_duration_ms: 平均时长
            - tools_usage: 工具使用统计
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

    def clear(self) -> None:
        """清空缓冲区"""
        self._trace_buffer.clear()

    @property
    def buffer_size(self) -> int:
        """缓冲区大小"""
        return len(self._trace_buffer)


__all__ = ["TraceEvaluator"]