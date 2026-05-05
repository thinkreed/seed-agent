"""
Harness 写冲突检测模块

提取并发写冲突检测逻辑，防止多个工具同时写入同一文件。

内容:
- check_write_conflicts - 检查并发写冲突
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 写操作工具名称集合
WRITE_TOOLS = {"file_write", "file_edit"}


def check_write_conflicts(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """检查并发写冲突

    Args:
        tool_calls: 工具调用列表

    Returns:
        如果存在冲突，返回错误结果列表；否则返回 None
    """
    seen_paths: dict[str, str] = {}

    for tc in tool_calls:
        tool_name = tc.get("function", {}).get("name", "")
        if tool_name not in WRITE_TOOLS:
            continue

        try:
            raw_args = tc.get("function", {}).get("arguments", "{}")
            args = (
                json.loads(raw_args)
                if isinstance(raw_args, str)
                else raw_args
            )
            path = args.get("path", "")
            if path:
                if path in seen_paths:
                    logger.warning(f"Concurrent write conflict detected: {path}")
                    return [
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", "unknown"),
                            "content": f"Error: Concurrent write conflict on '{path}'",
                        }
                        for tc in tool_calls
                    ]
                seen_paths[path] = tc.get("id", "unknown")
        except Exception as e:
            logger.debug(f"Failed to parse tool args: {e}")

    return None