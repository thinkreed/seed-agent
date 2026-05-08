"""
SemanticIndex build/rebuild operations.

Extracted from semantic_index.py for modularity.
Handles TF-IDF vocabulary building and FAISS index creation.
"""

import logging

import numpy as np

logger = logging.getLogger("seed_agent")


def build_index(
    texts: list[str],
    encoder,
    dim: int,
) -> tuple:
    """
    Build TF-IDF vocabulary and FAISS index from texts.

    Args:
        texts: List of document texts
        encoder: TFIDFEncoder instance
        dim: Target dimension for dimensionality reduction

    Returns:
        Tuple of (faiss_index, svd_model, effective_dim)
    """
    import faiss

    if not texts:
        return None, None, 0

    encoder.fit(texts)

    raw_dim = len(encoder.vocab)
    vectors = []
    for text in texts:
        vec = encoder.transform(text)
        vectors.append(vec)

    if not vectors:
        return None, None, 0

    all_vectors = np.vstack(vectors).astype(np.float32)

    # Create FAISS index
    if raw_dim <= dim:
        faiss_index = faiss.IndexFlatIP(raw_dim)
        faiss_index.add(all_vectors)
        return faiss_index, None, raw_dim

    # Dimensionality reduction needed
    from sklearn.decomposition import TruncatedSVD

    n_samples = all_vectors.shape[0]
    n_components = min(dim, raw_dim - 1, n_samples - 1)
    n_components = max(1, n_components)

    svd_model = TruncatedSVD(n_components=n_components, random_state=42)
    reduced = svd_model.fit_transform(all_vectors).astype(np.float32)
    norms = np.linalg.norm(reduced, axis=1, keepdims=True)
    norms[norms == 0] = 1
    reduced = reduced / norms

    faiss_index = faiss.IndexFlatIP(n_components)
    faiss_index.add(reduced)

    return faiss_index, svd_model, n_components


def rebuild_index_from_texts(
    original_texts: dict[str, str],
    encoder,
    dim: int,
) -> tuple:
    """
    Rebuild index from stored original texts.

    Args:
        original_texts: Dict of doc_id -> text
        encoder: TFIDFEncoder instance
        dim: Target dimension

    Returns:
        Tuple of (faiss_index, svd_model, effective_dim, doc_ids)
    """
    if not original_texts:
        return None, None, 0, []

    items = list(original_texts.items())
    doc_ids = [doc_id for doc_id, _ in items]
    texts = [text for _, text in items]

    index, svd, effective_dim = build_index(texts, encoder, dim)

    return index, svd, effective_dim, doc_ids


def apply_changes_to_texts(
    original_texts: dict[str, str],
    changes: dict[str, list[str]],
    texts_map: dict[str, str],
) -> None:
    """
    Apply changes to original_texts dict in place.

    Args:
        original_texts: Original texts storage (modified in place)
        changes: Changes dict with added/removed/modified
        texts_map: Text content for changed documents
    """
    # Remove deleted documents
    for doc_id in changes.get("removed", []):
        if doc_id in original_texts:
            del original_texts[doc_id]

    # Add new documents
    for doc_id in changes.get("added", []):
        if doc_id in texts_map:
            original_texts[doc_id] = texts_map[doc_id]

    # Update modified documents
    for doc_id in changes.get("modified", []):
        if doc_id in texts_map:
            original_texts[doc_id] = texts_map[doc_id]


__all__ = [
    "build_index",
    "rebuild_index_from_texts",
    "apply_changes_to_texts",
]