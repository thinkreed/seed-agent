"""
上下文压缩工具函数

包含消息处理、Token估算、简化等辅助函数
"""

import logging
from typing import Any

from src.session_event_stream import EventType

logger = logging.getLogger(__name__)


def estimate_tokens(messages: list[dict[str, Any]], token_per_char: float) -> int:
    """估算 Token 数

    Args:
        messages: 消息列表
        token_per_char: 每字符Token系数

    Returns:
        int: 估算的Token数
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            # 使用字符数 * 系数估算
            total += int(len(content) * token_per_char)

        # Tool calls 也计入
        if msg.get("tool_calls"):
            tc_str = str(msg["tool_calls"])
            total += int(len(tc_str) * token_per_char)

    return total


def event_to_message(event: dict[str, Any]) -> dict[str, Any] | None:
    """将事件转换为消息格式

    Args:
        event: 事件字典

    Returns:
        dict | None: 消息字典，或None（如果事件无法转换）
    """
    event_type = event["type"]
    data = event["data"]

    if event_type == EventType.USER_INPUT.value:
        return {"role": "user", "content": data.get("content", "")}

    if event_type == EventType.LLM_RESPONSE.value:
        msg: dict[str, Any] = {"role": "assistant"}
        content = data.get("content")
        if content:
            msg["content"] = content
        if data.get("tool_calls"):
            msg["tool_calls"] = data["tool_calls"]
        return msg

    if event_type == EventType.TOOL_RESULT.value:
        return {
            "role": "tool",
            "tool_call_id": data.get("tool_call_id"),
            "content": data.get("content", ""),
        }

    return None


def build_history_from_session(
    session: Any,
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """从 Session 构建完整历史（包括摘要）

    Args:
        session: SessionEventStream 实例
        system_prompt: 系统提示

    Returns:
        list: 消息列表
    """
    messages: list[dict[str, Any]] = []

    # 系统提示
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # 获取最近的摘要标记
    last_summary = session.find_last_summary_marker()

    # 添加摘要作为上下文
    if last_summary:
        summary_content = last_summary["data"].get("summary", "")
        if summary_content:
            messages.append(
                {"role": "user", "content": f"[历史摘要]\n{summary_content}"}
            )

    # 获取摘要后的事件
    recent_events = session.get_events_since_last_summary(
        [EventType.USER_INPUT, EventType.LLM_RESPONSE, EventType.TOOL_RESULT]
    )

    # 转换事件为消息
    for event in recent_events:
        msg = event_to_message(event)
        if msg:
            messages.append(msg)

    return messages


def simplify_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """简化消息（提取关键信息）

    Args:
        messages: 消息列表

    Returns:
        list: 简化后的消息列表
    """
    simplified = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if not content:
            continue

        # 提取关键信息
        key_info = extract_key_info(content)
        if key_info:
            simplified.append({"role": role, "key_info": key_info})

    return simplified


def extract_key_info(content: str) -> str:
    """提取内容的关键信息

    Args:
        content: 内容字符串

    Returns:
        str: 关键信息
    """
    # 限制长度
    max_len = 100
    if len(content) <= max_len:
        return content

    # 提取关键句子（包含特定关键词）
    keywords = ["完成", "成功", "错误", "Error", "result", "输出", "创建", "修改"]
    sentences = content.split("\n")

    key_sentences = [
        sentence[:max_len]
        for sentence in sentences
        if any(kw in sentence for kw in keywords)
    ]

    if key_sentences:
        return "\n".join(key_sentences[:3])

    # 无关键词时返回首尾
    return content[:50] + "..." + content[-50:]


def format_simplified(simplified: list[dict[str, Any]]) -> str:
    """格式化简化摘要

    Args:
        simplified: 简化后的消息列表

    Returns:
        str: 格式化后的摘要字符串
    """
    lines = []
    for item in simplified[:10]:  # 最多 10 条
        role = item.get("role", "")
        key_info = item.get("key_info", "")
        lines.append(f"- [{role}]: {key_info[:80]}")

    return "\n".join(lines)


def format_abstract(simplified: list[dict[str, Any]]) -> str:
    """格式化简短摘要

    Args:
        simplified: 简化后的消息列表

    Returns:
        str: 格式化后的摘要字符串
    """
    # 统计信息
    user_count = sum(1 for i in simplified if i.get("role") == "user")
    assistant_count = sum(1 for i in simplified if i.get("role") == "assistant")
    tool_count = sum(1 for i in simplified if i.get("role") == "tool")

    return (
        f"早期对话: {user_count} 条用户输入, "
        f"{assistant_count} 条响应, {tool_count} 条工具调用"
    )


def format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """格式化消息用于摘要

    Args:
        messages: 消息列表

    Returns:
        str: 格式化后的字符串
    """
    lines = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if not content:
            if msg.get("tool_calls"):
                tc_names = [
                    tc.get("function", {}).get("name", "")
                    for tc in msg["tool_calls"]
                ]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            else:
                continue

        # 限制长度
        if len(content) > 200:
            content = content[:200] + "..."

        lines.append(f"{role}: {content}")

    return "\n".join(lines)