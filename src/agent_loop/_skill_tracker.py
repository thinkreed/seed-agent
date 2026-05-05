"""
AgentLoop Skill Outcome 记录

职责:
- 记录 load_skill 工具结果
- 提取触发信号
- 评估并记录执行结果
"""

import logging

from src.session_event_stream import EventType
from src.tools.memory_tools import _record_skill_outcome

logger = logging.getLogger(__name__)


class SkillTracker:
    """Skill 结果追踪器"""

    def __init__(self, session, session_id: str):
        self.session = session
        self.session_id = session_id
        self._pending_skill_outcomes: list[dict] = []

    def record_load_skill_if_needed(
        self, tool_name: str, tool_args: dict, tool_id: str, content: str, failed: bool
    ) -> None:
        """记录 load_skill 结果"""
        if tool_name == "load_skill":
            self._pending_skill_outcomes.append(
                {
                    "skill_name": tool_args.get("name", ""),
                    "tool_call_id": tool_id,
                    "result": content,
                    "signals": self._extract_signals_from_events(),
                    **({"failed": True} if failed else {}),
                }
            )

    def _extract_signals_from_events(self) -> list[str]:
        """从最近事件提取触发信号"""
        signals = []
        recent_events = self.session.get_events(start_id=-5)

        for event in recent_events:
            if event["type"] == EventType.USER_INPUT.value:
                content = event["data"].get("content", "")
                if content:
                    words = content.split()[:5]
                    signals.extend(words)

        return signals[:10]

    def evaluate_and_record_skill_outcomes(self, final_success: bool) -> None:
        """评估并记录 Skill 执行结果"""
        for outcome in self._pending_skill_outcomes:
            skill_name = outcome.get("skill_name", "")
            if not skill_name:
                continue

            result = outcome.get("result", "")
            failed = outcome.get("failed", False)
            signals = outcome.get("signals", [])

            outcome_status, score = self._evaluate_skill_outcome(
                result, failed, final_success
            )

            _record_skill_outcome(
                skill_name=skill_name,
                outcome=outcome_status,
                score=score,
                signals=signals,
                session_id=self.session_id,
                context=f"Event stream session: {self.session_id}",
            )

        self._pending_skill_outcomes.clear()

    def _evaluate_skill_outcome(
        self, result: str, failed: bool, final_success: bool
    ) -> tuple[str, float]:
        """评估单个 Skill 结果"""
        if failed:
            return "failed", 0.0

        if final_success:
            if "Error:" in result or "error" in result.lower():
                return "partial", 0.5
            return "success", 1.0

        return "partial", 0.7

    def get_pending_count(self) -> int:
        """获取待处理的 outcome 数量"""
        return len(self._pending_skill_outcomes)

    def clear_pending(self) -> None:
        """清除待处理的 outcomes"""
        self._pending_skill_outcomes.clear()