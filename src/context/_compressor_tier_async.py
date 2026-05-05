"""
上下文压缩异步层级操作

包含 Tier 1/2/3 的异步压缩实现（使用 LLM）
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.context._compressor_prompts import (
    ABSTRACT_SUMMARY_PROMPT,
    LIGHT_SUMMARY_PROMPT,
)
from src.context._compressor_format import (
    format_abstract,
    format_messages_for_summary,
    format_simplified,
    simplify_messages,
)

logger = logging.getLogger(__name__)


async def apply_tier_1_and_2_async(
    history: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """Tier 1 + Tier 2: 异步版本"""
    tier_1_messages = tier_1_keep_rounds * 2
    tier_2_messages = tier_2_keep_rounds * 2

    tier_1 = (
        history[-tier_1_messages:] if len(history) > tier_1_messages else history
    )

    tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
    tier_2_end = len(history) - tier_1_messages
    tier_2 = history[tier_2_start:tier_2_end]

    compressed = []

    if tier_2:
        light_summary = await light_summarize(tier_2, gateway, model_id)
        if light_summary:
            compressed.append(
                {"role": "system", "content": f"[中等对话摘要]\n{light_summary}"}
            )

    compressed.extend(tier_1)

    return compressed


async def apply_all_tiers_async(
    history: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """完整三层: 异步版本"""
    tier_1_messages = tier_1_keep_rounds * 2
    tier_2_messages = tier_2_keep_rounds * 2

    tier_1 = (
        history[-tier_1_messages:] if len(history) > tier_1_messages else history
    )

    tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
    tier_2_end = len(history) - tier_1_messages
    tier_2 = history[tier_2_start:tier_2_end]

    tier_3 = history[:tier_2_start]

    compressed = []

    if tier_3:
        abstract = await abstract_summarize(tier_3, gateway, model_id)
        if abstract:
            compressed.append(
                {"role": "system", "content": f"[历史摘要 - 简短]\n{abstract}"}
            )

    if tier_2:
        light_summary = await light_summarize(tier_2, gateway, model_id)
        if light_summary:
            compressed.append(
                {"role": "system", "content": f"[中等对话摘要]\n{light_summary}"}
            )

    compressed.extend(tier_1)

    return compressed


async def light_summarize(
    messages: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
) -> str | None:
    """轻量总结: 保留主要操作和结果"""
    formatted = format_messages_for_summary(messages)

    if not formatted:
        return None

    prompt = LIGHT_SUMMARY_PROMPT.format(messages=formatted)

    try:
        response = await gateway.chat_completion(
            model_id, [{"role": "user", "content": prompt}], tools=None
        )
        choices = response.get("choices", [])
        if not choices:
            logger.warning("Light summary: LLM returned empty choices")
            return format_simplified(simplify_messages(messages))
        summary = choices[0].get("message", {}).get("content", "")
        if not summary:
            return format_simplified(simplify_messages(messages))
        return summary.strip()
    except Exception as e:
        logger.warning(f"Light summary generation failed: {type(e).__name__}: {e}")
        return format_simplified(simplify_messages(messages))


async def abstract_summarize(
    messages: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
) -> str | None:
    """简短摘要: 仅保留核心结论"""
    formatted = format_messages_for_summary(messages)

    if not formatted:
        return None

    prompt = ABSTRACT_SUMMARY_PROMPT.format(messages=formatted)

    try:
        response = await gateway.chat_completion(
            model_id, [{"role": "user", "content": prompt}], tools=None
        )
        choices = response.get("choices", [])
        if not choices:
            logger.warning("Abstract summary: LLM returned empty choices")
            return format_abstract(simplify_messages(messages))
        summary = choices[0].get("message", {}).get("content", "")
        if not summary:
            return format_abstract(simplify_messages(messages))
        return summary.strip()
    except Exception as e:
        logger.warning(f"Abstract summary generation failed: {type(e).__name__}: {e}")
        return format_abstract(simplify_messages(messages))