"""LLM 推理结果封装

ReasonResult: 推理结果封装类
_parse_model_id: 模型 ID 解析辅助函数
"""

from typing import Any


def parse_model_id(model_id: str) -> tuple[str, str]:
    """解析 model_id 为 (provider, model_name)

    Args:
        model_id: 模型标识符，格式如 "provider/model-name"

    Returns:
        (provider, model_name) 元组，若无 provider 则返回 ("unknown", model_id)
    """
    if "/" in model_id:
        parts = model_id.split("/", 1)
        return parts[0], parts[1]
    return "unknown", model_id


class ReasonResult:
    """推理结果封装"""

    def __init__(
        self,
        response: dict[str, Any],
        model_id: str,
        duration_ms: float,
        tokens_used: int | None = None,
    ):
        self.response = response
        self.model_id = model_id
        self.duration_ms = duration_ms
        self.tokens_used = tokens_used

    def get_content(self) -> str:
        """获取响应内容"""
        choices = self.response.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    def get_tool_calls(self) -> list[dict] | None:
        """获取工具调用"""
        choices = self.response.get("choices", [])
        if not choices:
            return None
        return choices[0].get("message", {}).get("tool_calls")

    def is_tool_call(self) -> bool:
        """是否包含工具调用"""
        return bool(self.get_tool_calls())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return self.response