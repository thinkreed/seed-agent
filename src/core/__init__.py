"""
Core 模块

提供核心功能：
- SemanticIndex: 语义搜索索引（TF-IDF + FAISS）
- TFIDFEncoder: TF-IDF 编码器
"""

from ._encoder import TFIDFEncoder
from .semantic_index import SemanticIndex

__all__ = ["SemanticIndex", "TFIDFEncoder"]