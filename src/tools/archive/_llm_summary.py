"""
LLM 摘要生成

基于 Hermes Agent LLM 摘要设计：
- 核心结论 1-2 句话总结
- 关键发现 3-5 条提取
- 支持 LLM Gateway 或简单摘要

核心功能：
- generate_summary: LLM 生成核心结论摘要
- extract_key_findings: 提取关键发现
- format_events_for_summary: 格式化事件用于摘要
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


def format_events_for_summary(events: list[dict[str, Any]]) -> str:
    """格式化事件用于摘要生成

    Args:
        events: 事件列表

    Returns:
        格式化的文本
    """
    lines = []

    for event in events:
        event_type = event.get("type", "")
        event_data = event.get("data", {})

        if event_type == "user_input":
            lines.append(f"用户: {event_data.get('content', '')[:200]}")
        elif event_type == "llm_response":
            content = event_data.get("content", "")
            if content:
                lines.append(f"助手: {content[:300]}")
        elif event_type == "tool_call":
            tool_name = event_data.get("function", {}).get("name", "unknown")
            lines.append(f"调用工具: {tool_name}")
        elif event_type == "tool_result":
            lines.append(f"工具结果: {event_data.get('content', '')[:100]}")

    return chr(10).join(lines)


def simple_summary(events: list[dict[str, Any]]) -> str:
    """简单摘要（无 LLM 时使用）

    Args:
        events: 事件列表

    Returns:
        基础摘要
    """
    user_inputs = [e for e in events if e.get("type") == "user_input"]

    if user_inputs:
        first_input = user_inputs[0].get("data", {}).get("content", "")[:100]
        return f"会话包含 {len(events)} 个事件，用户请求: {first_input}"

    return f"会话包含 {len(events)} 个事件"


def simple_findings(events: list[dict[str, Any]]) -> list[str]:
    """简单发现提取（无 LLM 时使用）

    Args:
        events: 事件列表

    Returns:
        发现列表
    """
    findings = []

    # 提取工具调用
    tool_events = [e for e in events if e.get("type") == "tool_call"]
    if tool_events:
        tools_used = set()
        for e in tool_events:
            tool_name = e.get("data", {}).get("function", {}).get("name", "unknown")
            tools_used.add(tool_name)
        findings.append(f"使用了工具: {', '.join(tools_used)}")

    # 提取错误
    error_events = [e for e in events if e.get("type") == "error_occurred"]
    if error_events:
        findings.append(f"发生了 {len(error_events)} 个错误")

    return findings


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