"""
Harness 流式处理类型定义

定义流式响应的 chunk 类型和常量。

内容:
- StreamChunkType - 流式 chunk 类型枚举
- StreamChunk - 流式响应 chunk TypedDict
- IterationResult - 单轮迭代结果 TypedDict
"""

from typing import Any, TypedDict


class StreamChunkType:
    """流式 chunk 类型常量"""

    CHUNK = "chunk"  # 文本片段
    TOOL_START = "tool_start"  # 工具开始
    TOOL_END = "tool_end"  # 工具结束
    AWAITING_USER_INPUT = "awaiting_user_input"  # 等待用户输入
    CANCELLED = "cancelled"  # 执行取消
    FINAL = "final"  # 最终响应
    ERROR = "error"  # 错误


class StreamChunk(TypedDict, total=False):
    """流式响应 chunk

    根据 type 字段有不同的结构：
    - chunk: {"type": "chunk", "content": "..."}
    - tool_start: {"type": "tool_start", "tool_name": "..."}
    - tool_end: {"type": "tool_end", "result": "..."}
    - awaiting_user_input: {"type": "awaiting_user_input", "request": {...}}
    - cancelled: {"type": "cancelled", "reason": "..."}
    - final: {"type": "final", "content": "..."}
    - error: {"type": "error", "content": "..."}
    """

    type: str
    content: str
    tool_name: str
    result: str
    request: dict[str, Any]
    reason: str


class IterationResult(TypedDict):
    """单轮迭代结果

    Attributes:
        full_content: LLM 响应文本
        tool_calls: 累积的工具调用列表
        duration_ms: 执行时长（毫秒）
    """

    full_content: str
    tool_calls: list[dict[str, Any]]
    duration_ms: float