"""
Lightweight semantic search index using TF-IDF + FAISS.
No external embedding API required - works offline.

Architecture inspired by Claude Context hybrid search pattern:
  - TF-IDF for dense vector representation
  - FAISS IndexFlatIP for cosine similarity (Inner Product)
  - L2 normalization enables IP = cosine similarity

重构说明:
- TFIDFEncoder 移至 _encoder.py
- Persistence 移至 _persist.py
- Incremental update 移至 _incremental.py
- SemanticIndex 保留核心索引逻辑 (build/search)

Usage:
    idx = SemanticIndex(dim=128)
    idx.add("doc1", "text content here")
    idx.build()
    results = idx.search("query text", top_k=3)

    # P5 增量更新
    idx.remove("doc1")
    idx.add("doc1", "new content")
    idx.incremental_build()
"""

import logging

import numpy as np

from ._encoder import TFIDFEncoder
from ._incremental import (
    add_vector_to_index,
    process_incremental_changes,
    remove_doc,
    should_full_rebuild,
)
from ._persist import (
    load_faiss_index,
    load_index_metadata,
    load_svd_model,
    save_index,
)

logger = logging.getLogger("seed_agent")


class SemanticIndex:
    """
    Semantic search index: TF-IDF vectors stored in FAISS for similarity search.

    Args:
        dim: Output dimension (FAISS will project if TF-IDF dim differs)
        index_path: Path to persist index (None = in-memory only)
    """

    def __init__(self, dim: int = 128, index_path: str | None = None):
        self.dim = dim
        self.index_path = index_path
        self.encoder = TFIDFEncoder()
        self.index = None  # FAISS index
        self.svd = None  # SVD model for dimensionality reduction
        self.doc_ids: list[str] = []
        self._built = False
        self._effective_dim: int = 0
        self._original_texts: dict[str, str] = {}

    def add(self, doc_id: str, text: str) -> None:
        """Add a document to the index (before build)."""
        self.doc_ids.append(doc_id)
        if not hasattr(self, "_texts"):
            self._texts = []
        self._texts.append(text)

    def add_batch(self, items: list[tuple[str, str]]) -> None:
        """Add multiple documents at once."""
        for doc_id, text in items:
            self.add(doc_id, text)

    def build(self) -> None:
        """Build the TF-IDF vocabulary and FAISS index."""
        import faiss

        if not hasattr(self, "_texts") or not self._texts:
            return

        self.encoder.fit(self._texts)

        raw_dim = len(self.encoder.vocab)
        vectors = []
        for text in self._texts:
            vec = self.encoder.transform(text)
            vectors.append(vec)

        if not vectors:
            return

        all_vectors = np.vstack(vectors).astype(np.float32)

        # Create FAISS index
        if raw_dim <= self.dim:
            faiss_index = faiss.IndexFlatIP(raw_dim)
            faiss_index.add(all_vectors)
            self.index = faiss_index
            self._effective_dim = raw_dim
        else:
            from sklearn.decomposition import TruncatedSVD

            n_samples = all_vectors.shape[0]
            n_components = min(self.dim, raw_dim - 1, n_samples - 1)
            n_components = max(1, n_components)

            svd_model = TruncatedSVD(n_components=n_components, random_state=42)
            reduced = svd_model.fit_transform(all_vectors).astype(np.float32)
            norms = np.linalg.norm(reduced, axis=1, keepdims=True)
            norms[norms == 0] = 1
            reduced = reduced / norms

            faiss_index = faiss.IndexFlatIP(n_components)
            faiss_index.add(reduced)
            self.index = faiss_index
            self.svd = svd_model
            self._effective_dim = n_components

        self._built = True
        # Store original texts for rebuild
        for doc_id, text in zip(self.doc_ids, self._texts, strict=True):
            self._original_texts[doc_id] = text
        del self._texts

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search for semantically similar documents."""
        if not self._built or self.index is None:
            return []

        query_vec = self.encoder.transform(query).astype(np.float32)

        if self.svd is not None:
            query_vec = self.svd.transform(query_vec).astype(np.float32)
            norm = np.linalg.norm(query_vec)
            if norm > 0:
                query_vec = query_vec / norm
        elif query_vec.shape[1] != self.index.d:
            raw_dim = query_vec.shape[1]
            if raw_dim < self.index.d:
                padded = np.zeros((1, self.index.d), dtype=np.float32)
                padded[:, :raw_dim] = query_vec
                query_vec = padded
            else:
                query_vec = query_vec[:, : self.index.d]

        k = min(top_k, len(self.doc_ids))
        scores, indices = self.index.search(query_vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0], strict=True):
            if idx >= 0 and idx < len(self.doc_ids):
                results.append({
                    "doc_id": self.doc_ids[idx],
                    "score": float(score),
                    "rank": len(results) + 1,
                })
        return results

    # === P5 增量更新方法 ===

    def remove(self, doc_id: str) -> bool:
        """移除文档（标记删除）。"""
        return remove_doc(self.doc_ids, doc_id)

    def update(self, doc_id: str, new_text: str) -> bool:
        """更新文档内容（延迟更新，需调用 incremental_build）。"""
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
        """增量构建索引（小变更增量，大变更重建）。"""
        if not self._built:
            self.build()
            return

        if changes is None:
            if not hasattr(self, "_pending_updates") or not self._pending_updates:
                return
            changes = {
                "added": [],
                "removed": [],
                "modified": list(self._pending_updates.keys()),
            }
            texts_map = self._pending_updates.copy()
            self._pending_updates = {}

        added = changes.get("added", [])
        removed = changes.get("removed", [])
        modified = changes.get("modified", [])

        # 大变更 → 完整重建
        if should_full_rebuild(added, removed, modified, len(self.doc_ids)):
            logger.info(
                f"Large change ({len(added) + len(removed) + len(modified)}/{len(self.doc_ids)}), rebuilding index"
            )
            self._rebuild_with_changes(changes, texts_map or {})
            return

        # 小变更 → 增量更新
        logger.info(
            f"Small change ({len(added) + len(removed) + len(modified)}/{len(self.doc_ids)}), incremental update"
        )
        process_incremental_changes(
            self.index,
            self.encoder,
            self.svd,
            self.doc_ids,
            changes,
            texts_map or {},
            self._original_texts,
        )

    def _rebuild_with_changes(
        self,
        changes: dict[str, list[str]],
        texts_map: dict[str, str],
    ) -> None:
        """完整重建索引，处理变更。"""
        # Remove deleted documents
        for doc_id in changes.get("removed", []):
            remove_doc(self.doc_ids, doc_id)
            if doc_id in self._original_texts:
                del self._original_texts[doc_id]

        # Add new documents
        for doc_id in changes.get("added", []):
            if doc_id in texts_map:
                self._original_texts[doc_id] = texts_map[doc_id]

        # Update modified documents
        for doc_id in changes.get("modified", []):
            if doc_id in texts_map:
                self._original_texts[doc_id] = texts_map[doc_id]

        # Rebuild
        if self._original_texts:
            items = list(self._original_texts.items())
            self.doc_ids = []
            self.index = None
            self.svd = None
            self._built = False
            self.add_batch(items)
            self.build()

    def rebuild(self) -> None:
        """强制完整重建索引。"""
        if self._original_texts:
            items = list(self._original_texts.items())
            self.doc_ids = []
            self.index = None
            self.svd = None
            self._built = False
            self.add_batch(items)
            self.build()

    # === Persistence ===

    def save(self, path: str | None = None) -> str:
        """Persist index to disk."""
        save_path = path or self.index_path
        if not save_path:
            raise ValueError("No save path specified")

        return save_index(
            self.index,
            self.encoder,
            self.svd,
            self.doc_ids,
            self.dim,
            self._effective_dim,
            save_path,
            self._original_texts,
        )

    @classmethod
    def load(cls, path: str) -> "SemanticIndex":
        """Load persisted index from disk."""
        idx = cls(dim=128, index_path=path)
        idx.index = load_faiss_index(path)
        meta = load_index_metadata(path)

        idx.dim = meta["dim"]
        idx._effective_dim = meta.get("effective_dim", meta["dim"])
        idx.doc_ids = meta["doc_ids"]
        idx.encoder.vocab = meta["vocab"]
        idx.encoder.idf = meta["idf"]
        idx.encoder._doc_count = meta["doc_count"]
        idx._original_texts = meta.get("original_texts", {})
        idx._built = True

        if meta.get("has_svd"):
            idx.svd = load_svd_model(path)

        return idx

    def __len__(self) -> int:
        return len(self.doc_ids)

    @property
    def is_built(self) -> bool:
        return self._built


__all__ = ["SemanticIndex", "TFIDFEncoder"]