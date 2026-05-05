"""LLMClient (大脑) 模块

重构版本：原大文件已拆分为多个小模块
此文件保留为向后兼容的导入入口

详细文档请参阅 llm_client/__init__.py 和子模块

模块结构:
- llm_client/_result.py: ReasonResult 类、辅助函数 (~50 行)
- llm_client/_client.py: LLMClient 核心类 (~140 行)
- llm_client/_pool.py: LLMClientPool 池类 (~100 行)

总计: 3 个模块，每个均 < 150 行
"""

# 向后兼容：从新模块导入并导出
from src.llm_client import (
    LLMClient,
    LLMClientPool,
    ReasonResult,
    parse_model_id,
)

__all__ = ["LLMClient", "LLMClientPool", "ReasonResult", "parse_model_id"]