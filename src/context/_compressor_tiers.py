"""
上下文压缩层级操作

包含 Tier 1/2/3 的同步和异步压缩实现
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.context._compressor_prompts import (
    ABSTRACT_SUMMARY_PROMPT,
    LIGHT_SUMMARY_PROMPT,
)
from src.context._compressor_utils import (
    format_abstract,
    format_messages_for_summary,
    format_simplified,
    simplify_messages,
)
from src.context._config import CompressionTier

logger = logging.getLogger(__name__)


def apply_tier_1_only(
    history: list[dict[str, Any]],
    tier_1_keep_rounds: int,
) -> list[dict[str, Any]]:
    """仅 Tier 1: 最新轮完整保留

    Args:
        history: 完整历史消息
        tier_1_keep_rounds: Tier 1 保留轮数

    Returns:
        list: 压缩后的消息列表
    """
    keep_messages = tier_1_keep_rounds * 2  # 一轮 ≈ 2 条消息

    # 保留系统提示和摘要
    system_and_summary = [
        m
        for m in history
        if m["role"] in ["system", "user"] and "摘要" in m.get("content", "")
    ]

    # 最新消息
    recent = history[-keep_messages:] if len(history) > keep_messages else history

    # 合并，去重
    compressed = system_and_summary[:]
    for m in recent:
        if m not in compressed:
            compressed.append(m)

    return compressed


def apply_tier_1_and_2_sync(
    history: list[dict[str, Any]],
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """Tier 1 + Tier 2: 同步版本（不使用 LLM）

    Args:
        history: 完整历史消息
        tier_1_keep_rounds: Tier 1 保留轮数
        tier_2_keep_rounds: Tier 2 保留轮数

    Returns:
        list: 压缩后的消息列表
    """
    tier_1_messages = tier_1_keep_rounds * 2
    tier_2_messages = tier_2_keep_rounds * 2

    # Tier 1: 最新完整保留
    tier_1 = (
        history[-tier_1_messages:] if len(history) > tier_1_messages else history
    )

    # Tier 2: 稍旧部分
    tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
    tier_2_end = len(history) - tier_1_messages
    tier_2 = history[tier_2_start:tier_2_end]

    compressed = []

    # Tier 2: 简化格式（不使用 LLM）
    if tier_2:
        simplified = simplify_messages(tier_2)
        if simplified:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[中等对话摘要]\n{format_simplified(simplified)}",
                }
            )

    # Tier 1
    compressed.extend(tier_1)

    return compressed


async def apply_tier_1_and_2_async(
    history: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """Tier 1 + Tier 2: 异步版本（使用 LLM 生成摘要）

    Args:
        history: 完整历史消息
        gateway: LLM Gateway 实例
        model_id: 模型 ID
        tier_1_keep_rounds: Tier 1 保留轮数
        tier_2_keep_rounds: Tier 2 保留轮数

    Returns:
        list: 压缩后的消息列表
    """
    tier_1_messages = tier_1_keep_rounds * 2
    tier_2_messages = tier_2_keep_rounds * 2

    # Tier 1: 最新完整保留
    tier_1 = (
        history[-tier_1_messages:] if len(history) > tier_1_messages else history
    )

    # Tier 2: 稍旧部分
    tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
    tier_2_end = len(history) - tier_1_messages
    tier_2 = history[tier_2_start:tier_2_end]

    compressed = []

    # Tier 2: 使用 LLM 轻量总结
    if tier_2:
        light_summary = await light_summarize(tier_2, gateway, model_id)
        if light_summary:
            compressed.append(
                {"role": "system", "content": f"[中等对话摘要]\n{light_summary}"}
            )

    # Tier 1
    compressed.extend(tier_1)

    return compressed


def apply_all_tiers_sync(
    history: list[dict[str, Any]],
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """完整三层: 同步版本

    Args:
        history: 完整历史消息
        tier_1_keep_rounds: Tier 1 保留轮数
        tier_2_keep_rounds: Tier 2 保留轮数

    Returns:
        list: 压缩后的消息列表
    """
    tier_1_messages = tier_1_keep_rounds * 2
    tier_2_messages = tier_2_keep_rounds * 2

    # Tier 1: 最新
    tier_1 = (
        history[-tier_1_messages:] if len(history) > tier_1_messages else history
    )

    # Tier 2: 稍旧
    tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
    tier_2_end = len(history) - tier_1_messages
    tier_2 = history[tier_2_start:tier_2_end]

    # Tier 3: 更早
    tier_3 = history[:tier_2_start]

    compressed = []

    # Tier 3: 简短摘要（简化）
    if tier_3:
        abstract = simplify_messages(tier_3)
        if abstract:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[历史摘要 - 简短]\n{format_abstract(abstract)}",
                }
            )

    # Tier 2: 轻量总结（简化）
    if tier_2:
        simplified = simplify_messages(tier_2)
        if simplified:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[中等对话摘要]\n{format_simplified(simplified)}",
                }
            )

    # Tier 1
    compressed.extend(tier_1)

    return compressed


async def apply_all_tiers_async(
    history: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """完整三层: 异步版本（使用 LLM）

    Args:
        history: 完整历史消息
        gateway: LLM Gateway 实例
        model_id: 模型 ID
        tier_1_keep_rounds: Tier 1 保留轮数
        tier_2_keep_rounds: Tier 2 保留轮数

    Returns:
        list: 压缩后的消息列表
    """
    tier_1_messages = tier_1_keep_rounds * 2
    tier_2_messages = tier_2_keep_rounds * 2

    # Tier 1: 最新
    tier_1 = (
        history[-tier_1_messages:] if len(history) > tier_1_messages else history
    )

    # Tier 2: 稍旧
    tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
    tier_2_end = len(history) - tier_1_messages
    tier_2 = history[tier_2_start:tier_2_end]

    # Tier 3: 更早
    tier_3 = history[:tier_2_start]

    compressed = []

    # Tier 3: 使用 LLM 简短摘要
    if tier_3:
        abstract = await abstract_summarize(tier_3, gateway, model_id)
        if abstract:
            compressed.append(
                {"role": "system", "content": f"[历史摘要 - 简短]\n{abstract}"}
            )

    # Tier 2: 使用 LLM 轻量总结
    if tier_2:
        light_summary = await light_summarize(tier_2, gateway, model_id)
        if light_summary:
            compressed.append(
                {"role": "system", "content": f"[中等对话摘要]\n{light_summary}"}
            )

    # Tier 1
    compressed.extend(tier_1)

    return compressed


async def light_summarize(
    messages: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
) -> str | None:
    """轻量总结: 保留主要操作和结果（使用 LLM）

    Args:
        messages: 消息列表
        gateway: LLM Gateway 实例
        model_id: 模型 ID

    Returns:
        str | None: 摘要字符串，或None
    """
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
            simplified = simplify_messages(messages)
            return format_simplified(simplified)
        summary = choices[0].get("message", {}).get("content", "")
        if not summary:
            simplified = simplify_messages(messages)
            return format_simplified(simplified)
        return summary.strip()
    except Exception as e:
        logger.warning(f"Light summary generation failed: {type(e).__name__}: {e}")
        # Fallback: 使用简化版本
        simplified = simplify_messages(messages)
        return format_simplified(simplified)


async def abstract_summarize(
    messages: list[dict[str, Any]],
    gateway: "LLMGateway",
    model_id: str,
) -> str | None:
    """简短摘要: 仅保留核心结论（使用 LLM）

    Args:
        messages: 消息列表
        gateway: LLM Gateway 实例
        model_id: 模型 ID

    Returns:
        str | None: 摘要字符串，或None
    """
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
            simplified = simplify_messages(messages)
            return format_abstract(simplified)
        summary = choices[0].get("message", {}).get("content", "")
        if not summary:
            simplified = simplify_messages(messages)
            return format_abstract(simplified)
        return summary.strip()
    except Exception as e:
        logger.warning(
            f"Abstract summary generation failed: {type(e).__name__}: {e}"
        )
        # Fallback: 使用统计版本
        simplified = simplify_messages(messages)
        return format_abstract(simplified)