"""
上下文压缩格式化模块

包含消息简化、关键信息提取、格式化输出
"""

from typing import Any


def simplify_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """简化消息（提取关键信息）"""
    simplified = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if not content:
            continue

        key_info = extract_key_info(content)
        if key_info:
            simplified.append({"role": role, "key_info": key_info})

    return simplified


def extract_key_info(content: str) -> str:
    """提取内容的关键信息"""
    max_len = 100
    if len(content) <= max_len:
        return content

    keywords = ["完成", "成功", "错误", "Error", "result", "输出", "创建", "修改"]
    sentences = content.split("\n")

    key_sentences = [
        sentence[:max_len]
        for sentence in sentences
        if any(kw in sentence for kw in keywords)
    ]

    if key_sentences:
        return "\n".join(key_sentences[:3])

    return content[:50] + "..." + content[-50:]


def format_simplified(simplified: list[dict[str, Any]]) -> str:
    """格式化简化摘要"""
    lines = []
    for item in simplified[:10]:
        role = item.get("role", "")
        key_info = item.get("key_info", "")
        lines.append(f"- [{role}]: {key_info[:80]}")

    return "\n".join(lines)


def format_abstract(simplified: list[dict[str, Any]]) -> str:
    """格式化简短摘要"""
    user_count = sum(1 for i in simplified if i.get("role") == "user")
    assistant_count = sum(1 for i in simplified if i.get("role") == "assistant")
    tool_count = sum(1 for i in simplified if i.get("role") == "tool")

    return (
        f"早期对话: {user_count} 条用户输入, "
        f"{assistant_count} 条响应, {tool_count} 条工具调用"
    )


def format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """格式化消息用于摘要"""
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

        if len(content) > 200:
            content = content[:200] + "..."

        lines.append(f"{role}: {content}")

    return "\n".join(lines)