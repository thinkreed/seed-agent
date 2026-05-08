"""
Semantic search index: TF-IDF + FAISS. No external embedding API required.

拆分模块: _encoder.py, _persist.py, _incremental.py, _semantic_build.py, _semantic_search.py
"""

import logging

import numpy as np

from ._encoder import TFIDFEncoder
from ._incremental import (
    prepare_incremental_changes,
    process_incremental_changes,
    remove_doc,
    should_full_rebuild,
)
from ._persist import load_semantic_index, save_index
from ._semantic_build import apply_changes_to_texts, build_index, rebuild_index_from_texts
from ._semantic_search import search_index

logger = logging.getLogger("seed_agent")


class SemanticIndex:
    """Semantic search index: TF-IDF vectors stored in FAISS."""

    def __init__(self, dim: int = 128, index_path: str | None = None):
        self.dim = dim
        self.index_path = index_path
        self.encoder = TFIDFEncoder()
        self.index = None
        self.svd = None
        self.doc_ids: list[str] = []
        self._built = False
        self._effective_dim: int = 0
        self._original_texts: dict[str, str] = {}

    def add(self, doc_id: str, text: str) -> None:
        """Add a document to the index."""
        self.doc_ids.append(doc_id)
        if not hasattr(self, "_texts"):
            self._texts = []
        self._texts.append(text)

    def add_batch(self, items: list[tuple[str, str]]) -> None:
        """Add multiple documents."""
        for doc_id, text in items:
            self.add(doc_id, text)

    def build(self) -> None:
        """Build TF-IDF vocabulary and FAISS index."""
        if not hasattr(self, "_texts") or not self._texts:
            return

        self.index, self.svd, self._effective_dim = build_index(
            self._texts, self.encoder, self.dim
        )
        self._built = True

        for doc_id, text in zip(self.doc_ids, self._texts, strict=True):
            self._original_texts[doc_id] = text
        del self._texts

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search for similar documents."""
        if not self._built or self.index is None:
            return []
        query_vec = self.encoder.transform(query).astype(np.float32)
        return search_index(self.index, query_vec, self.svd, self.doc_ids, top_k)

    def remove(self, doc_id: str) -> bool:
        """Remove document (mark deletion)."""
        return remove_doc(self.doc_ids, doc_id)

    def update(self, doc_id: str, new_text: str) -> bool:
        """Update document text (deferred)."""
        if doc_id not in self.doc_ids:
            return False
        if not hasattr(self, "_pending_updates"):
            self._pending_updates: dict[str, str] = {}
        self._pending_updates[doc_id] = new_text
        return True

    def incremental_build(
        self,
        changes: dict[str, list[str]] | None = None,
        texts_map: dict[str, str] | None = None,
    ) -> None:
        """Incremental build: small changes incremental, large changes rebuild."""
        if not self._built:
            self.build()
            return

        if changes is None:
            pending = getattr(self, "_pending_updates", None)
            changes, texts_map = prepare_incremental_changes(pending)
            self._pending_updates = {}
            if not changes:
                return

        added, removed, modified = (
            changes.get("added", []),
            changes.get("removed", []),
            changes.get("modified", []),
        )

        if should_full_rebuild(added, removed, modified, len(self.doc_ids)):
            logger.info(f"Large change, rebuilding")
            self._rebuild_with_changes(changes, texts_map or {})
        else:
            logger.info(f"Small change, incremental")
            process_incremental_changes(
                self.index, self.encoder, self.svd, self.doc_ids,
                changes, texts_map or {}, self._original_texts,
            )

    def _rebuild_with_changes(
        self, changes: dict[str, list[str]], texts_map: dict[str, str]
    ) -> None:
        """Full rebuild with changes."""
        apply_changes_to_texts(self._original_texts, changes, texts_map)
        if self._original_texts:
            self.index, self.svd, self._effective_dim, self.doc_ids = (
                rebuild_index_from_texts(self._original_texts, self.encoder, self.dim)
            )
            self._built = True

    def rebuild(self) -> None:
        """Force full rebuild."""
        if self._original_texts:
            self.index, self.svd, self._effective_dim, self.doc_ids = (
                rebuild_index_from_texts(self._original_texts, self.encoder, self.dim)
            )
            self._built = True

    def save(self, path: str | None = None) -> str:
        """Persist index to disk."""
        save_path = path or self.index_path
        if not save_path:
            raise ValueError("No save path specified")
        return save_index(
            self.index, self.encoder, self.svd, self.doc_ids,
            self.dim, self._effective_dim, save_path, self._original_texts,
        )

    @classmethod
    def load(cls, path: str) -> "SemanticIndex":
        """Load persisted index from disk."""
        idx = cls(dim=128, index_path=path)
        idx.index, idx.encoder, idx.svd, meta = load_semantic_index(path, TFIDFEncoder)
        idx.dim = meta["dim"]
        idx._effective_dim = meta.get("effective_dim", meta["dim"])
        idx.doc_ids = meta["doc_ids"]
        idx._original_texts = meta.get("original_texts", {})
        idx._built = True
        return idx

    def __len__(self) -> int:
        return len(self.doc_ids)

    @property
    def is_built(self) -> bool:
        return self._built


__all__ = ["SemanticIndex", "TFIDFEncoder"]