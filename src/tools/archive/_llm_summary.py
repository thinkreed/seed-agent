"""
LLM 摘要生成

基于 Hermes Agent LLM 摘要设计：
- 核心结论 1-2 句话总结
- 关键发现 3-5 条提取
- 支持 LLM Gateway 或简单摘要

聚合格式化和生成函数。
"""

from typing import Any

from src.tools.archive._llm_summary_format import (
    format_events_for_summary,
    simple_findings,
    simple_summary,
)
from src.tools.archive._llm_summary_generate import extract_key_findings, generate_summary

__all__ = [
    "format_events_for_summary",
    "simple_summary",
    "simple_findings",
    "generate_summary",
    "extract_key_findings",
]