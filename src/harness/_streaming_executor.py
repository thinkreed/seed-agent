"""
Harness 流式执行器

提取核心流式 LLM 推理逻辑。

内容:
- stream_llm_reasoning - 流式 LLM 推理执行（含 thinking 支持）
- execute_iteration - 执行单轮迭代
"""

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.request_queue import RequestPriority

from ._streaming_types import IterationResult, StreamChunkType
from ._streaming_utils import collect_tool_calls, process_tool_delta

if TYPE_CHECKING:
    from src.llm_client import LLMClient


async def stream_llm_reasoning(
    llm_client: "LLMClient",
    context: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    priority: int = RequestPriority.CRITICAL,
) -> AsyncGenerator[tuple[str, dict[int, dict[str, Any]] | None], None]:
    """流式 LLM 推理

    Args:
        llm_client: LLMClient 实例
        context: 消息上下文
        tools: 工具 schemas
        priority: 请求优先级

    Yields:
        (content_chunk, tool_call_delta) 元组
        - content_chunk: 文本片段（可能为空字符串）
        - tool_call_delta: 工具调用增量（可能为 None）
    """
    tool_calls_accumulator: dict[int, dict[str, Any]] = {}

    async for chunk in llm_client.stream_reason(context, tools=tools, priority=priority):
        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})

        # 处理文本内容
        content = delta.get("content", "")
        if content:
            yield (content, None)

        # 处理工具调用
        tc_list = delta.get("tool_calls")
        if tc_list:
            process_tool_delta(tc_list, tool_calls_accumulator)
            yield ("", tool_calls_accumulator)

    # 最终返回完整的累积器
    yield ("", tool_calls_accumulator)


async def execute_iteration(
    llm_client: "LLMClient",
    context: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    priority: int = RequestPriority.CRITICAL,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行单轮 LLM 迭代（含 thinking 支持）

    Args:
        llm_client: LLMClient 实例
        context: 消息上下文
        tools: 工具 schemas
        priority: 请求优先级

    Yields:
        流式 chunk:
            - {"type": "thinking", "content": "..."} - 思考过程片段
            - {"type": "chunk", "content": "..."} - 文本片段
            - {"type": "tool_start", "tool_name": "..."} - 工具开始
            - {"_iteration_result": True, ...} - 迭代结果（内部使用）
    """
    full_content = ""
    full_thinking = ""
    tool_calls_accumulator: dict[int, dict[str, Any]] = {}

    start_time = time.time()

    async for chunk in llm_client.stream_reason(context, tools=tools, priority=priority):
        # 处理 thinking 类型 chunk（来自 client/_streaming.py）
        if chunk.get("type") == "thinking":
            thinking_content = chunk.get("content", "")
            if thinking_content:
                full_thinking += thinking_content
                yield {"type": StreamChunkType.THINKING, "content": thinking_content}
            continue

        # 处理 content 类型 chunk
        if chunk.get("type") == "content":
            content = chunk.get("content", "")
            if content:
                full_content += content
                yield {"type": StreamChunkType.CHUNK, "content": content}
            continue

        # 处理原始 OpenAI 格式 chunk（向后兼容）
        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})

        # 识别 thinking/reasoning_content 字段（兼容不同模型）
        thinking = delta.get("thinking") or delta.get("reasoning_content")
        if thinking:
            full_thinking += thinking
            yield {"type": StreamChunkType.THINKING, "content": thinking}

        # 处理文本内容
        content = delta.get("content")
        if content:
            full_content += content
            yield {"type": StreamChunkType.CHUNK, "content": content}

        # 处理工具调用
        tc_list = delta.get("tool_calls")
        if tc_list:
            process_tool_delta(tc_list, tool_calls_accumulator)
            for tc in tc_list:
                if tc.get("function", {}).get("name"):
                    yield {"type": StreamChunkType.TOOL_START, "tool_name": tc["function"]["name"]}

    duration_ms = (time.time() - start_time) * 1000
    tool_calls = collect_tool_calls(tool_calls_accumulator)

    # 返回最终结果（通过特殊 key 传递，调用方需要检查）
    yield {
        "_iteration_result": True,
        "full_content": full_content,
        "full_thinking": full_thinking,
        "tool_calls": tool_calls,
        "duration_ms": duration_ms,
    }


def is_iteration_result(chunk: dict[str, Any]) -> bool:
    """检查是否为迭代结果 chunk

    Args:
        chunk: 流式 chunk

    Returns:
        是否为迭代结果
    """
    return chunk.get("_iteration_result") is True


def extract_iteration_result(chunk: dict[str, Any]) -> IterationResult:
    """提取迭代结果

    Args:
        chunk: 包含迭代结果的 chunk

    Returns:
        IterationResult TypedDict
    """
    return {
        "full_content": chunk["full_content"],
        "tool_calls": chunk["tool_calls"],
        "duration_ms": chunk["duration_ms"],
    }