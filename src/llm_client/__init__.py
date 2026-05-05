"""LLMClient 模块入口

重构版本：将大文件拆分为多个小模块
此文件保留为向后兼容的导入入口

模块结构:
- _result.py: ReasonResult 类 (~59 行)
- _span.py: OpenTelemetry 辅助 (~60 行)
- _client.py: LLMClient 核心类 (~120 行)
- _pool.py: LLMClientPool 池类 (~141 行)

总计: 4 个模块，每个均 < 150 行
"""

from ._client import LLMClient
from ._pool import LLMClientPool
from ._result import ReasonResult, parse_model_id

__all__ = ["LLMClient", "LLMClientPool", "ReasonResult", "parse_model_id"]