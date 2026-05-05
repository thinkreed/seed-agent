"""
用户建模辩证更新层

职责:
- 冲突检测
- 内部推理讨论
- 模型升级决策
"""

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ._db import get_db

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


class DialecticEngine:
    """辩证更新引擎"""

    def __init__(self, llm_gateway: "LLMGateway | None" = None):
        self._llm_gateway = llm_gateway

    def set_llm_gateway(self, gateway: "LLMGateway") -> None:
        """设置 LLM Gateway"""
        self._llm_gateway = gateway

    async def detect_conflicts(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """检测新证据与旧模型的矛盾"""
        conflicts = []

        # 收集偏好键
        pref_keys = set()
        for obs in observations:
            if obs["type"] == "preference":
                key = obs["data"].get("key")
                if key:
                    pref_keys.add(key)

        # 批量获取偏好
        db = get_db()
        existing_prefs = db.get_preferences_batch(pref_keys) if pref_keys else {}

        for obs in observations:
            if obs["type"] != "preference":
                continue

            pref_key = obs["data"].get("key")
            pref_value = obs["data"].get("value")

            if not pref_key or not pref_value:
                continue

            existing = existing_prefs.get(pref_key)

            if existing and self._is_conflicting(existing, pref_value, obs["context"]):
                conflicts.append(
                    {
                        "preference_key": pref_key,
                        "old_belief": existing,
                        "new_evidence": pref_value,
                        "confidence_old": existing.get("confidence", 0.8),
                        "confidence_new": obs["confidence"],
                        "context": obs["context"],
                        "observation_id": obs["id"],
                    }
                )

        return conflicts

    def _is_conflicting(
        self, existing: dict[str, Any], new_value: str, context: str | None
    ) -> bool:
        """检查是否矛盾"""
        usual = existing.get("usual", existing.get("value"))

        if new_value == usual:
            return False

        # 检查例外情况
        exceptions = existing.get("exceptions", {})
        if context:
            for exc_key, exc_value in exceptions.items():
                if (
                    exc_key in context or context in exc_key
                ) and new_value == exc_value.get("value"):
                    return False

        return True

    async def reason_about_conflicts(
        self, conflicts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """内部推理讨论"""
        if not self._llm_gateway:
            return self._simple_resolution(conflicts)

        prompt = self._build_reasoning_prompt(conflicts)

        try:
            result = await self._llm_gateway.chat_completion(
                model_id="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                priority=2,
            )

            response_text = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return self._parse_resolution_response(response_text, conflicts)
        except Exception as e:
            logger.warning(f"LLM reasoning failed: {type(e).__name__}: {e}")
            return self._simple_resolution(conflicts)

    def _build_reasoning_prompt(self, conflicts: list[dict[str, Any]]) -> str:
        """构建推理 prompt"""
        conflict_descs = []
        for c in conflicts:
            conflict_descs.append(
                f"- 原有认知: 用户偏好 '{c['preference_key']}' = "
                f"'{c['old_belief'].get('usual', c['old_belief'].get('value'))}' "
                f"(置信度 {c['confidence_old']:.2f})"
            )
            conflict_descs.append(
                f"- 新证据: 观察到 '{c['new_evidence']}' "
                f"(置信度 {c['confidence_new']:.2f}, 上下文: {c['context'] or '无'})"
            )

        return f"""作为用户建模专家，分析以下矛盾并给出升级方案。

矛盾列表:
{chr(10).join(conflict_descs)}

请分析:
1. 这是真正的偏好改变，还是特定上下文下的例外情况？
2. 如何升级用户模型（不是简单覆盖，而是保留例外）？

请以 JSON 格式返回:
{
    "resolutions": [
        {
            "preference_key": "...",
            "resolution_type": "exception" | "upgrade",
            "value": "...",
            "when": "例外条件（如果 resolution_type=exception）",
            "reason": "推理理由",
            "confidence": 0.XX
        }
    ]
}
"""

    def _parse_resolution_response(
        self, response: str, conflicts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """解析 LLM 返回的决议"""
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM resolution response")

        return self._simple_resolution(conflicts)

    def _simple_resolution(self, conflicts: list[dict[str, Any]]) -> dict[str, Any]:
        """简单规则决议"""
        resolutions = []

        for c in conflicts:
            context = c.get("context", "")

            if context:
                resolutions.append(
                    {
                        "preference_key": c["preference_key"],
                        "resolution_type": "exception",
                        "value": c["new_evidence"],
                        "when": context[:100],
                        "reason": "有明确上下文，视为例外情况",
                        "confidence": min(c["confidence_old"], c["confidence_new"]),
                    }
                )
            else:
                resolutions.append(
                    {
                        "preference_key": c["preference_key"],
                        "resolution_type": "upgrade",
                        "value": c["new_evidence"],
                        "when": "",
                        "reason": "无上下文约束，视为偏好升级",
                        "confidence": c["confidence_new"],
                    }
                )

        return {"resolutions": resolutions}

    def record_dialectical_history(
        self,
        conflicts: list[dict[str, Any]],
        resolution: dict[str, Any],
        updates: list[dict[str, Any]],
    ) -> None:
        """记录辩证进化历史"""
        timestamp = datetime.now(tz=UTC).isoformat()

        conflict_json = json.dumps(conflicts, ensure_ascii=False)
        resolution_json = json.dumps(resolution, ensure_ascii=False)
        update_json = json.dumps(updates, ensure_ascii=False)

        db = get_db()
        db._ensure_conn().execute(
            """
            INSERT INTO dialectical_history (conflict, resolution, update_record, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (conflict_json, resolution_json, update_json, timestamp),
        )
        db._ensure_conn().commit()

    def get_dialectical_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取辩证进化历史"""
        db = get_db()
        rows = (
            db._ensure_conn()
            .execute(
                """
            SELECT id, conflict, resolution, update_record, timestamp, reasoning_log
            FROM dialectical_history
            ORDER BY timestamp DESC
            LIMIT ?
        """,
                (limit,),
            )
            .fetchall()
        )

        return [
            {
                "id": row["id"],
                "conflict": json.loads(row["conflict"]),
                "resolution": json.loads(row["resolution"]),
                "update": json.loads(row["update_record"]),
                "timestamp": row["timestamp"],
                "reasoning_log": row["reasoning_log"],
            }
            for row in rows
        ]


# 单例
_dialectic_engine: DialecticEngine | None = None


def get_dialectic_engine() -> DialecticEngine:
    """获取辩证引擎单例"""
    global _dialectic_engine
    if _dialectic_engine is None:
        _dialectic_engine = DialecticEngine()
    return _dialectic_engine