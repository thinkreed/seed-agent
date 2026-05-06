"""
Lightweight semantic search index using TF-IDF + FAISS.
No external embedding API required - works offline.

Architecture inspired by Claude Context hybrid search pattern:
  - TF-IDF for dense vector representation
  - FAISS IndexFlatIP for cosine similarity (Inner Product)
  - L2 normalization enables IP = cosine similarity

重构说明:
- TFIDFEncoder 移至 _encoder.py
- SemanticIndex 保留核心索引逻辑

Usage:
    idx = SemanticIndex(dim=128)
    idx.add("doc1", "text content here")
    idx.build()
    results = idx.search("query text", top_k=3)
"""

import json
import logging
from pathlib import Path

import numpy as np

from ._encoder import TFIDFEncoder

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

    def save(self, path: str | None = None) -> str:
        """Persist index to disk."""
        save_path = path or self.index_path
        if not save_path:
            raise ValueError("No save path specified")

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        import faiss

        try:
            faiss.write_index(self.index, save_path)
        except (OSError, RuntimeError):
            logger.exception(f"Failed to write FAISS index to {save_path}")
            raise

        meta_path = save_path + ".meta"
        meta = {
            "dim": self.dim,
            "effective_dim": self._effective_dim,
            "doc_ids": self.doc_ids,
            "vocab": self.encoder.vocab,
            "idf": self.encoder.idf,
            "doc_count": self.encoder._doc_count,
        }

        if self.svd is not None:
            svd_path = save_path + ".svd.npz"
            try:
                np.savez(
                    svd_path,
                    components=self.svd.components_,
                    explained_variance=self.svd.explained_variance_,
                    explained_variance_ratio=self.svd.explained_variance_ratio_,
                    singular_values=self.svd.singular_values_,
                    n_components=self.svd.n_components,
                )
                meta["has_svd"] = True
            except (OSError, ValueError) as e:
                logger.warning(f"Failed to save SVD model to {svd_path}: {e}")

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except OSError:
            logger.exception(f"Failed to write metadata to {meta_path}")
            raise

        return save_path

    @classmethod
    def load(cls, path: str) -> "SemanticIndex":
        """Load persisted index from disk."""
        import faiss

        idx = cls(dim=128, index_path=path)
        try:
            idx.index = faiss.read_index(path)
        except (OSError, RuntimeError):
            logger.exception(f"Failed to read FAISS index from {path}")
            raise

        meta_path = path + ".meta"
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.exception(f"Failed to load metadata from {meta_path}")
            raise

        idx.dim = meta["dim"]
        idx._effective_dim = meta.get("effective_dim", meta["dim"])
        idx.doc_ids = meta["doc_ids"]
        idx.encoder.vocab = meta["vocab"]
        idx.encoder.idf = meta["idf"]
        idx.encoder._doc_count = meta["doc_count"]
        idx._built = True

        if meta.get("has_svd"):
            svd_path = path + ".svd.npz"
            try:
                svd_data = np.load(svd_path, allow_pickle=False)
                from sklearn.decomposition import TruncatedSVD

                n_components = int(svd_data["n_components"])
                svd_model = TruncatedSVD(n_components=n_components, random_state=42)
                svd_model.components_ = svd_data["components"]
                svd_model.explained_variance_ = svd_data["explained_variance"]
                svd_model.explained_variance_ratio_ = svd_data[
                    "explained_variance_ratio"
                ]
                svd_model.singular_values_ = svd_data["singular_values"]
                idx.svd = svd_model
            except (OSError, KeyError, ValueError) as e:
                logger.warning(f"Failed to load SVD model from {svd_path}: {e}")
                idx.svd = None

        return idx

    def __len__(self) -> int:
        return len(self.doc_ids)

    @property
    def is_built(self) -> bool:
        return self._built


__all__ = ["SemanticIndex", "TFIDFEncoder"]