"""
上下文压缩同步层级操作

包含 Tier 1/2/3 的同步压缩实现
"""

from typing import Any

from src.context._compressor_format import (
    format_abstract,
    format_simplified,
    simplify_messages,
)


def apply_tier_1_only(
    history: list[dict[str, Any]],
    tier_1_keep_rounds: int,
) -> list[dict[str, Any]]:
    """仅 Tier 1: 最新轮完整保留"""
    keep_messages = tier_1_keep_rounds * 2

    system_and_summary = [
        m
        for m in history
        if m["role"] in ["system", "user"] and "摘要" in m.get("content", "")
    ]

    recent = history[-keep_messages:] if len(history) > keep_messages else history

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
    """Tier 1 + Tier 2: 同步版本"""
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
        simplified = simplify_messages(tier_2)
        if simplified:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[中等对话摘要]\n{format_simplified(simplified)}",
                }
            )

    compressed.extend(tier_1)

    return compressed


def apply_all_tiers_sync(
    history: list[dict[str, Any]],
    tier_1_keep_rounds: int,
    tier_2_keep_rounds: int,
) -> list[dict[str, Any]]:
    """完整三层: 同步版本"""
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
        abstract = simplify_messages(tier_3)
        if abstract:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[历史摘要 - 简短]\n{format_abstract(abstract)}",
                }
            )

    if tier_2:
        simplified = simplify_messages(tier_2)
        if simplified:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[中等对话摘要]\n{format_simplified(simplified)}",
                }
            )

    compressed.extend(tier_1)

    return compressed