"""
SemanticIndex load operations.

Extracted from _persist.py for modularity.
Handles loading FAISS index and metadata.
"""

import json
import logging

import numpy as np

logger = logging.getLogger("seed_agent")


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
    "load_index_metadata",
    "load_faiss_index",
    "load_svd_model",
    "load_semantic_index",
]