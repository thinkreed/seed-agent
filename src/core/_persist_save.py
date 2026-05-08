"""
SemanticIndex save operations.

Extracted from _persist.py for modularity.
Handles saving FAISS index and metadata.
"""

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger("seed_agent")


def save_index(
    index,
    encoder,
    svd,
    doc_ids: list[str],
    dim: int,
    effective_dim: int,
    save_path: str,
    original_texts: dict[str, str] | None = None,
) -> str:
    """
    Persist FAISS index and metadata to disk.

    Args:
        index: FAISS index object
        encoder: TFIDFEncoder instance
        svd: TruncatedSVD model (optional)
        doc_ids: List of document IDs
        dim: Configured dimension
        effective_dim: Actual dimension used
        save_path: Target file path
        original_texts: Original texts for rebuild (optional)

    Returns:
        Path to saved index file
    """
    import faiss

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        faiss.write_index(index, save_path)
    except (OSError, RuntimeError):
        logger.exception(f"Failed to write FAISS index to {save_path}")
        raise

    meta_path = save_path + ".meta"
    meta = {
        "dim": dim,
        "effective_dim": effective_dim,
        "doc_ids": doc_ids,
        "vocab": encoder.vocab,
        "idf": encoder.idf,
        "doc_count": encoder._doc_count,
        "original_texts": original_texts or {},
    }

    if svd is not None:
        _save_svd_model(save_path, svd, meta)

    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except OSError:
        logger.exception(f"Failed to write metadata to {meta_path}")
        raise

    return save_path


def _save_svd_model(save_path: str, svd, meta: dict) -> None:
    """Save SVD model to .svd.npz file."""
    svd_path = save_path + ".svd.npz"
    try:
        np.savez(
            svd_path,
            components=svd.components_,
            explained_variance=svd.explained_variance_,
            explained_variance_ratio=svd.explained_variance_ratio_,
            singular_values=svd.singular_values_,
            n_components=svd.n_components,
        )
        meta["has_svd"] = True
    except (OSError, ValueError) as e:
        logger.warning(f"Failed to save SVD model to {svd_path}: {e}")


__all__ = ["save_index"]