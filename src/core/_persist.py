"""
SemanticIndex persistence operations.

Extracted from semantic_index.py for modularity.
Handles save/load of FAISS index and metadata.
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

    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except OSError:
        logger.exception(f"Failed to write metadata to {meta_path}")
        raise

    return save_path


def load_index_metadata(path: str) -> dict:
    """
    Load metadata from .meta file.

    Args:
        path: Index file path (without .meta extension)

    Returns:
        Metadata dictionary
    """
    meta_path = path + ".meta"
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.exception(f"Failed to load metadata from {meta_path}")
        raise


def load_faiss_index(path: str):
    """
    Load FAISS index from disk.

    Args:
        path: Index file path

    Returns:
        FAISS index object
    """
    import faiss

    try:
        return faiss.read_index(path)
    except (OSError, RuntimeError):
        logger.exception(f"Failed to read FAISS index from {path}")
        raise


def load_svd_model(path: str):
    """
    Load TruncatedSVD model from .svd.npz file.

    Args:
        path: Index file path (without .svd.npz extension)

    Returns:
        TruncatedSVD model or None if not found
    """
    svd_path = path + ".svd.npz"
    try:
        svd_data = np.load(svd_path, allow_pickle=False)
        from sklearn.decomposition import TruncatedSVD

        n_components = int(svd_data["n_components"])
        svd_model = TruncatedSVD(n_components=n_components, random_state=42)
        svd_model.components_ = svd_data["components"]
        svd_model.explained_variance_ = svd_data["explained_variance"]
        svd_model.explained_variance_ratio_ = svd_data["explained_variance_ratio"]
        svd_model.singular_values_ = svd_data["singular_values"]
        return svd_model
    except (OSError, KeyError, ValueError) as e:
        logger.warning(f"Failed to load SVD model from {svd_path}: {e}")
        return None


def load_semantic_index(path: str, encoder_class):
    """
    Load complete SemanticIndex from disk.

    Args:
        path: Index file path
        encoder_class: TFIDFEncoder class to instantiate

    Returns:
        Tuple of (index, encoder, svd, meta)
    """
    index = load_faiss_index(path)
    meta = load_index_metadata(path)

    encoder = encoder_class()
    encoder.vocab = meta["vocab"]
    encoder.idf = meta["idf"]
    encoder._doc_count = meta["doc_count"]

    svd = None
    if meta.get("has_svd"):
        svd = load_svd_model(path)

    return index, encoder, svd, meta


__all__ = [
    "save_index",
    "load_index_metadata",
    "load_faiss_index",
    "load_svd_model",
    "load_semantic_index",
]