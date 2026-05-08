"""
LLM 摘要生成函数

调用 LLM Gateway 生成核心结论和关键发现。
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.tools.archive._llm_summary_format import (
    format_events_for_summary,
    simple_findings,
    simple_summary,
)

logger = logging.getLogger(__name__)


async def generate_summary(
    events: list[dict[str, Any]],
    llm_gateway: "LLMGateway | None" = None,
) -> str:
    """LLM 生成核心结论摘要

    要求: 1-2 句话总结核心结论

    Args:
        events: 事件列表
        llm_gateway: LLM Gateway 实例（可选）

    Returns:
        摘要内容
    """
    history_text = format_events_for_summary(events)

    if not history_text:
        return "无内容摘要"

    if not llm_gateway:
        return simple_summary(events)

    prompt = f"""请用1-2句话总结以下对话的核心结论，保留最有价值的信息:

{history_text[:2000]}

摘要格式:
- 核心结论: ...
"""

    try:
        result = await llm_gateway.chat_completion(
            model_id="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            priority=2,  # HIGH
        )

        return (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "摘要生成失败")
        )
    except Exception as e:
        logger.warning(f"LLM summary failed: {type(e).__name__}: {e}")
        return simple_summary(events)


async def extract_key_findings(
    events: list[dict[str, Any]],
    llm_gateway: "LLMGateway | None" = None,
) -> list[str]:
    """提取关键发现

    Args:
        events: 事件列表
        llm_gateway: LLM Gateway 实例（可选）

    Returns:
        发现列表（最多 5 条）
    """
    history_text = format_events_for_summary(events)

    if not history_text:
        return []

    if not llm_gateway:
        return simple_findings(events)

    prompt = f"""从以下对话中提取3-5个关键发现:

{history_text[:2000]}

关键发现格式 (每行一个，简洁):
1. 发现内容
2. 发现内容
...
"""

    try:
        result = await llm_gateway.chat_completion(
            model_id="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            priority=2,  # HIGH
        )

        response = (
            result.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        findings = [line.strip() for line in response.split("\n") if line.strip()]
        return findings[:5]
    except Exception as e:
        logger.warning(f"LLM findings extraction failed: {type(e).__name__}: {e}")
        return simple_findings(events)


__all__ = ["generate_summary", "extract_key_findings"]