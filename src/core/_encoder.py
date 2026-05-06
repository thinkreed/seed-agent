"""
TF-IDF 编码器

Simple TF-IDF encoder without sklearn dependency.
Provides text to vector transformation using TF-IDF weighting.
"""

import logging
import math
import re
from collections import Counter

import numpy as np

logger = logging.getLogger("seed_agent")


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
            self.idf[self.vocab[token]] = math.log(
                (self._doc_count + 1) / (df + 1)
            ) + 1

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
        return re.findall(r"[a-z0-9]+", text.lower())


__all__ = ["TFIDFEncoder"]