"""
Core 模块

提供核心功能：
- SemanticIndex: 语义搜索索引（TF-IDF + FAISS）
- TFIDFEncoder: TF-IDF 编码器
- MerkleDAG: Merkle DAG 增量索引（P5 新增）
- MerkleDAGNode: Merkle DAG 节点（P5 新增）
- FileSynchronizer: 文件同步器（P5 新增）
- DataHub: Pub/Sub 数据分发中心（P5 新增）
- TopicPolicy: Topic 策略配置（P5 新增）
- QueryInvalidator: 失效策略管理器（P5 新增）
"""

from ._datahub import DataHub, get_datahub
from ._datahub_types import TopicCategory, TopicEntry, TopicPolicy
from ._encoder import TFIDFEncoder
from ._file_synchronizer import FileSynchronizer
from ._merkle_dag import MerkleDAG, MerkleDAGNode
from ._query_invalidator import (
    CacheEntry,
    InvalidationEvent,
    QueryInvalidator,
    get_query_invalidator,
    setup_default_entities,
)
from .semantic_index import SemanticIndex

__all__ = [
    "SemanticIndex",
    "TFIDFEncoder",
    "MerkleDAG",
    "MerkleDAGNode",
    "FileSynchronizer",
    "DataHub",
    "get_datahub",
    "TopicCategory",
    "TopicPolicy",
    "TopicEntry",
    "QueryInvalidator",
    "get_query_invalidator",
    "setup_default_entities",
    "CacheEntry",
    "InvalidationEvent",
]