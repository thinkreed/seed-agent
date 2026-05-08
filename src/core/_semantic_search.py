"""
SemanticIndex search operations.

Extracted from semantic_index.py for modularity.
Handles query vector transformation and similarity search.
"""

import logging

import numpy as np

logger = logging.getLogger("seed_agent")


def prepare_query_vector(
    query_vec: np.ndarray,
    svd,
    index_dim: int,
) -> np.ndarray:
    """
    Prepare query vector for FAISS search.

    Applies SVD transformation and dimension adjustment.

    Args:
        query_vec: Raw TF-IDF query vector (1, raw_dim)
        svd: TruncatedSVD model (optional)
        index_dim: Target index dimension

    Returns:
        Prepared query vector (1, index_dim)
    """
    if svd is not None:
        query_vec = svd.transform(query_vec).astype(np.float32)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm
        return query_vec

    # Dimension adjustment without SVD
    raw_dim = query_vec.shape[1]
    if raw_dim < index_dim:
        padded = np.zeros((1, index_dim), dtype=np.float32)
        padded[:, :raw_dim] = query_vec
        return padded
    elif raw_dim > index_dim:
        return query_vec[:, :index_dim]

    return query_vec


def search_index(
    index,
    query_vec: np.ndarray,
    svd,
    doc_ids: list[str],
    top_k: int = 5,
) -> list[dict]:
    """
    Search FAISS index for similar documents.

    Args:
        index: FAISS index
        query_vec: Raw TF-IDF query vector
        svd: TruncatedSVD model (optional)
        doc_ids: List of document IDs
        top_k: Number of results to return

    Returns:
        List of result dicts with doc_id, score, rank
    """
    if index is None or not doc_ids:
        return []

    prepared_vec = prepare_query_vector(query_vec, svd, index.d)

    k = min(top_k, len(doc_ids))
    scores, indices = index.search(prepared_vec, k)

    results = []
    for score, idx in zip(scores[0], indices[0], strict=True):
        if 0 <= idx < len(doc_ids):
            results.append({
                "doc_id": doc_ids[idx],
                "score": float(score),
                "rank": len(results) + 1,
            })

    return results


__all__ = [
    "prepare_query_vector",
    "search_index",
]