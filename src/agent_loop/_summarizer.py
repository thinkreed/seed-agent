"""
AgentLoop 摘要机制

聚合适度和核心逻辑。

职责:
- 事件格式化摘要
- LLM 摘要生成
- 摘要触发判断
- 摘要标记创建
"""

from src.agent_loop._summarizer_core import Summarizer
from src.agent_loop._summarizer_types import SUMMARY_PROMPT

__all__ = ["SUMMARY_PROMPT", "Summarizer"]