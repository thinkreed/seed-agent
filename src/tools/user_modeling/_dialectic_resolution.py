"""
用户建模辩证更新层 - 推理决议

职责:
- LLM 推理讨论
- 决议解析
- 简单规则决议
"""

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


async def reason_about_conflicts(
    llm_gateway: "LLMGateway | None", conflicts: list[dict[str, Any]]
) -> dict[str, Any]:
    """内部推理讨论"""
    if not llm_gateway:
        return simple_resolution(conflicts)

    prompt = build_reasoning_prompt(conflicts)

    try:
        result = await llm_gateway.chat_completion(
            model_id="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            priority=2,
        )

        response_text = (
            result.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        return parse_resolution_response(response_text, conflicts)
    except Exception as e:
        logger.warning(f"LLM reasoning failed: {type(e).__name__}: {e}")
        return simple_resolution(conflicts)


def build_reasoning_prompt(conflicts: list[dict[str, Any]]) -> str:
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
{{
    "resolutions": [
        {{
            "preference_key": "...",
            "resolution_type": "exception" | "upgrade",
            "value": "...",
            "when": "例外条件（如果 resolution_type=exception）",
            "reason": "推理理由",
            "confidence": 0.XX
        }}
    ]
}}
"""


def parse_resolution_response(
    response: str, conflicts: list[dict[str, Any]]
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

    return simple_resolution(conflicts)


def simple_resolution(conflicts: list[dict[str, Any]]) -> dict[str, Any]:
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