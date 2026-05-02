"""
Lightweight semantic search index using TF-IDF + FAISS.
No external embedding API required - works offline.

Architecture inspired by Claude Context hybrid search pattern:
  - TF-IDF for dense vector representation
  - FAISS IndexFlatIP for cosine similarity (Inner Product)
  - L2 normalization enables IP = cosine similarity

Usage:
    idx = SemanticIndex(dim=128)
    idx.add("doc1", "text content here")
    idx.build()
    results = idx.search("query text", top_k=3)
"""

import json
import math
import pickle
from collections import Counter
from pathlib import Path

import numpy as np

# 类型注解使用内置类型


class TFIDFEncoder:
    """Simple TF-IDF encoder (no sklearn dependency)."""

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self.idf: list[float] = []
        self._doc_count: int = 0

    def fit(self, texts: list[str]) -> "TFIDFEncoder":
        """Build vocabulary and compute IDF from documents."""
        doc_freq: Counter[str] = Counter()
        self._doc_count = len(texts)

        for text in texts:
            tokens = set(self._tokenize(text))
            for t in tokens:
                doc_freq[t] += 1

        # Build vocab
        self.vocab = {t: i for i, t in enumerate(sorted(doc_freq.keys()))}
        vocab_size = len(self.vocab)

        # Compute IDF: log(N / df) + 1 (smoothed)
        self.idf = [0.0] * vocab_size
        for token, df in doc_freq.items():
            self.idf[self.vocab[token]] = math.log((self._doc_count + 1) / (df + 1)) + 1

        return self

    def transform(self, text: str) -> np.ndarray:
        """Transform text to TF-IDF vector."""
        dim = len(self.vocab)
        if dim == 0:
            return np.zeros((1, 1), dtype=np.float32)

        vec = np.zeros(dim, dtype=np.float32)
        tokens = self._tokenize(text)
        tf = Counter(tokens)

        for token, count in tf.items():
            if token in self.vocab:
                idx = self.vocab[token]
                # sublinear TF: 1 + log(tf)
                vec[idx] = (1 + math.log(count)) * self.idf[idx]

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec.reshape(1, -1).astype(np.float32)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenization: lowercase, split on non-alphanumeric."""
        import re
        return re.findall(r"[a-z0-9]+", text.lower())


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
        self.svd = None    # SVD model for dimensionality reduction
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

        # Fit TF-IDF encoder
        self.encoder.fit(self._texts)

        # Transform all documents
        raw_dim = len(self.encoder.vocab)
        vectors = []
        for text in self._texts:
            vec = self.encoder.transform(text)  # (1, raw_dim)
            vectors.append(vec)

        if not vectors:
            return

        all_vectors = np.vstack(vectors).astype(np.float32)  # (n_docs, raw_dim)

        # Create FAISS index (Inner Product = cosine sim after L2 norm)
        if raw_dim <= self.dim:
            # Direct: use raw vectors (no dimension reduction needed)
            faiss_index = faiss.IndexFlatIP(raw_dim)
            faiss_index.add(all_vectors)
            self.index = faiss_index
            self._effective_dim = raw_dim
        else:
            # Project to target dimension using SVD
            from sklearn.decomposition import TruncatedSVD
            n_samples = all_vectors.shape[0]
            # SVD components must be < min(raw_dim, n_samples)
            n_components = min(self.dim, raw_dim - 1, n_samples - 1)
            n_components = max(1, n_components)

            svd_model = TruncatedSVD(n_components=n_components, random_state=42)
            reduced = svd_model.fit_transform(all_vectors).astype(np.float32)
            # L2 normalize again after projection
            norms = np.linalg.norm(reduced, axis=1, keepdims=True)
            norms[norms == 0] = 1
            reduced = reduced / norms

            faiss_index = faiss.IndexFlatIP(n_components)
            faiss_index.add(reduced)
            self.index = faiss_index
            self.svd = svd_model
            self._effective_dim = n_components

        self._built = True
        del self._texts  # Free memory

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search for semantically similar documents."""
        if not self._built or self.index is None:
            return []

        query_vec = self.encoder.transform(query).astype(np.float32)

        # Project query to match FAISS index dimension
        if self.svd is not None:
            query_vec = self.svd.transform(query_vec).astype(np.float32)
            # L2 normalize after projection
            norm = np.linalg.norm(query_vec)
            if norm > 0:
                query_vec = query_vec / norm
        elif query_vec.shape[1] != self.index.d:
            # Fallback: pad or truncate
            raw_dim = query_vec.shape[1]
            if raw_dim < self.index.d:
                padded = np.zeros((1, self.index.d), dtype=np.float32)
                padded[:, :raw_dim] = query_vec
                query_vec = padded
            else:
                query_vec = query_vec[:, :self.index.d]

        k = min(top_k, len(self.doc_ids))
        scores, indices = self.index.search(query_vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.doc_ids):
                results.append({
                    "doc_id": self.doc_ids[idx],
                    "score": float(score),
                    "rank": len(results) + 1
                })
        return results

    def save(self, path: str | None = None) -> str:
        """Persist index to disk."""
        save_path = path or self.index_path
        if not save_path:
            raise ValueError("No save path specified")

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        import faiss
        faiss.write_index(self.index, save_path)

        # Save metadata + SVD model
        meta_path = save_path + ".meta"
        meta = {
            "dim": self.dim,
            "effective_dim": self._effective_dim,
            "doc_ids": self.doc_ids,
            "vocab": self.encoder.vocab,
            "idf": self.encoder.idf,
            "doc_count": self.encoder._doc_count,
        }

        # Save SVD model if exists
        if self.svd is not None:
            svd_path = save_path + ".svd.pkl"
            with open(svd_path, "wb") as f:
                pickle.dump(self.svd, f)
            meta["has_svd"] = True

        with open(meta_path, "w") as f:
            json.dump(meta, f)

        return save_path

    @classmethod
    def load(cls, path: str) -> "SemanticIndex":
        """Load persisted index from disk."""
        import faiss

        idx = cls(dim=128, index_path=path)
        idx.index = faiss.read_index(path)

        meta_path = path + ".meta"
        with open(meta_path, "r") as f:
            meta = json.load(f)

        idx.dim = meta["dim"]
        idx._effective_dim = meta.get("effective_dim", meta["dim"])
        idx.doc_ids = meta["doc_ids"]
        idx.encoder.vocab = meta["vocab"]
        idx.encoder.idf = meta["idf"]
        idx.encoder._doc_count = meta["doc_count"]
        idx._built = True

        # Load SVD model if exists
        if meta.get("has_svd"):
            svd_path = path + ".svd.pkl"
            with open(svd_path, "rb") as f:
                idx.svd = pickle.load(f)

        return idx

    def __len__(self) -> int:
        return len(self.doc_ids)

    @property
    def is_built(self) -> bool:
        return self._built
