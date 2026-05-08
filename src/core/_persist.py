"""
SemanticIndex persistence operations.

Aggregates save and load operations from split modules.
"""

from src.core._persist_load import (
    load_faiss_index,
    load_index_metadata,
    load_semantic_index,
    load_svd_model,
)
from src.core._persist_save import save_index

__all__ = [
    "save_index",
    "load_index_metadata",
    "load_faiss_index",
    "load_svd_model",
    "load_semantic_index",
]