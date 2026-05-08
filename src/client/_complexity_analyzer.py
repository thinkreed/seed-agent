"""复杂度分析器模块 - 从消息和上下文中提取复杂度特征"""

import re
from typing import Any


class ComplexityAnalyzer:
    """复杂度分析器 - 负责从消息和上下文中分析各维度复杂度"""

    def __init__(self, dimensions: dict, set_dimension_callback):
        self._dimensions = dimensions
        self._set_dimension = set_dimension_callback

    def analyze_code_complexity(self, messages: list[dict], context: dict[str, Any] | None) -> None:
        """分析代码复杂度"""
        code_context = context.get("code_context", {}) if context else {}

        if code_context:
            self._set_dimension("file_count", code_context.get("file_count", 0))
            self._set_dimension("line_count", code_context.get("line_count", 0))
            self._set_dimension("function_count", code_context.get("function_count", 0))
            self._set_dimension("nesting_depth", code_context.get("nesting_depth", 0))
            self._set_dimension("dependency_count", code_context.get("dependency_count", 0))
        else:
            self._infer_code_complexity(messages)

    def _infer_code_complexity(self, messages: list[dict]) -> None:
        """从消息推断代码复杂度"""
        total_content = ""
        for msg in messages:
            if msg.get("role") in ["user", "assistant"]:
                total_content += msg.get("content", "") + "\n"

        file_refs = re.findall(r'[\w/]+\.(py|js|ts|java|go|rs)', total_content)
        self._set_dimension("file_count", len(set(file_refs)))

        code_blocks = re.findall(r'```[\w]*\n(.*?)```', total_content, re.DOTALL)
        total_lines = sum(len(block.split('\n')) for block in code_blocks)
        self._set_dimension("line_count", total_lines)

        functions = re.findall(r'(def |function |func )', total_content)
        self._set_dimension("function_count", len(functions))

    def analyze_task_complexity(self, messages: list[dict], context: dict[str, Any] | None) -> None:
        """分析任务复杂度"""
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message += msg.get("content", "") + "\n"

        steps = re.findall(r'(首先|然后|接着|最后|first|second|then|finally)', user_message.lower())
        self._set_dimension("step_count", len(steps) // 2 + 1)

        decisions = re.findall(r'(如果|否则|判断|if|else|when|condition)', user_message.lower())
        self._set_dimension("decision_points", len(decisions))

        parallel_keywords = re.findall(r'(并行|同时|parallel|concurrent)', user_message.lower())
        self._set_dimension("parallel_tasks", len(parallel_keywords))

        if "验证" in user_message or "verify" in user_message.lower():
            self._set_dimension("verification_needed", 1.0)
        if "文档" in user_message or "document" in user_message.lower():
            self._set_dimension("documentation_needed", 1.0)
        if "测试" in user_message or "test" in user_message.lower():
            self._set_dimension("test_needed", 1.0)

    def analyze_context_complexity(self, messages: list[dict], context: dict[str, Any] | None) -> None:
        """分析上下文复杂度"""
        self._set_dimension("message_count", len(messages))

        total_tokens = sum(len(msg.get("content", "").split()) * 1.5 for msg in messages)
        self._set_dimension("token_count", total_tokens)

        total_content = ""
        for msg in messages:
            total_content += msg.get("content", "") + "\n"
        file_refs = re.findall(r'[\w/]+\.[\w]+', total_content)
        self._set_dimension("file_references", len(set(file_refs)))

        history_length = context.get("history_length", 0) if context else 0
        self._set_dimension("history_length", history_length)

    def analyze_tool_complexity(self, messages: list[dict], has_tools: bool, context: dict[str, Any] | None) -> None:
        """分析工具复杂度"""
        tool_context = context.get("tool_context", {}) if context else {}

        tool_count = tool_context.get("tool_count", 0)
        if has_tools and tool_count == 0:
            tool_count = 1
        self._set_dimension("tool_count", tool_count)

        self._set_dimension("tool_types", tool_context.get("tool_types", 1))
        cross_domain = tool_context.get("cross_domain", False)
        self._set_dimension("cross_domain_calls", 1.0 if cross_domain else 0.0)
        self._set_dimension("permission_level", tool_context.get("permission_level", 0))

    def analyze_knowledge_complexity(self, messages: list[dict], context: dict[str, Any] | None) -> None:
        """分析知识复杂度"""
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message += msg.get("content", "") + "\n"

        domain_keywords = re.findall(
            r'(架构|设计|安全|性能|测试|architecture|security|performance|testing)', user_message.lower())
        self._set_dimension("domain_count", len(set(domain_keywords)))

        concepts = re.findall(r'(概念|原理|机制|concept|principle|mechanism)', user_message.lower())
        self._set_dimension("concept_count", len(concepts))

        reasoning_keywords = re.findall(
            r'(分析|推断|推理|判断|analyze|infer|reason|judge)', user_message.lower())
        self._set_dimension("reasoning_depth", len(reasoning_keywords))

        uncertainty_keywords = re.findall(
            r'(不确定|可能|假设|假设|uncertain|maybe|assume|hypothesis)', user_message.lower())
        self._set_dimension("uncertainty_level", len(uncertainty_keywords))