"""
SemanticIndex incremental update operations.

Extracted from semantic_index.py for modularity.
Handles remove/update/incremental_build without full rebuild.

P5 新增: 基于 claude-context-docs 的增量索引设计
- 小变更（<30%）: 使用旧词汇表编码新文档
- 大变更（>=30%）: 完整重建
"""

import logging

import numpy as np

logger = logging.getLogger("seed_agent")


def remove_doc(doc_ids: list[str], doc_id: str) -> bool:
    """
    Remove document from index (mark deletion).

    Note: FAISS IndexFlatIP doesn't support true deletion.
    The vector remains in the index but doc_id is removed.
    Call rebuild after many deletions.

    Args:
        doc_ids: List of document IDs (modified in place)
        doc_id: Document ID to remove

    Returns:
        True if removed, False if not found
    """
    if doc_id in doc_ids:
        doc_ids.remove(doc_id)
        return True
    return False


def compute_change_ratio(
    added: list[str],
    removed: list[str],
    modified: list[str],
    total_docs: int,
) -> float:
    """
    Compute the ratio of changes to total documents.

    Args:
        added: Added document IDs
        removed: Removed document IDs
        modified: Modified document IDs
        total_docs: Total document count

    Returns:
        Change ratio (0.0 to 1.0+)
    """
    total_changes = len(added) + len(removed) + len(modified)
    if total_docs == 0:
        return 1.0 if total_changes > 0 else 0.0
    return total_changes / total_docs


def should_full_rebuild(
    added: list[str],
    removed: list[str],
    modified: list[str],
    total_docs: int,
    threshold: float = 0.3,
) -> bool:
    """
    Decide whether to full rebuild vs incremental update.

    Args:
        added: Added document IDs
        removed: Removed document IDs
        modified: Modified document IDs
        total_docs: Total document count
        threshold: Rebuild threshold (default 30%)

    Returns:
        True if should full rebuild
    """
    ratio = compute_change_ratio(added, removed, modified, total_docs)
    return ratio >= threshold


def add_vector_to_index(
    index,
    encoder,
    svd,
    doc_ids: list[str],
    doc_id: str,
    text: str,
) -> None:
    """
    Add a single vector to existing index.

    Uses existing vocabulary (encoder must be fitted).

    Args:
        index: FAISS index
        encoder: TFIDFEncoder (already fitted)
        svd: TruncatedSVD model (optional)
        doc_ids: Document ID list (modified in place)
        doc_id: New document ID
        text: Document text
    """
    if index is None:
        return

    vec = encoder.transform(text).astype(np.float32)

    if svd is not None:
        vec = svd.transform(vec).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

    # Adjust dimension
    if vec.shape[1] != index.d:
        if vec.shape[1] < index.d:
            padded = np.zeros((1, index.d), dtype=np.float32)
            padded[:, : vec.shape[1]] = vec
            vec = padded
        else:
            vec = vec[:, : index.d]

    index.add(vec)
    doc_ids.append(doc_id)


def process_incremental_changes(
    index,
    encoder,
    svd,
    doc_ids: list[str],
    changes: dict[str, list[str]],
    texts_map: dict[str, str],
    original_texts: dict[str, str],
) -> dict[str, list[str]]:
    """
    Process incremental changes without full rebuild.

    Args:
        index: FAISS index
        encoder: TFIDFEncoder
        svd: TruncatedSVD model
        doc_ids: Document ID list
        changes: Changes dict with added/removed/modified
        texts_map: Text content for changed documents
        original_texts: Original texts storage

    Returns:
        Processed changes dict
    """
    added = changes.get("added", [])
    removed = changes.get("removed", [])
    modified = changes.get("modified", [])

    # Remove documents
    for doc_id in removed:
        remove_doc(doc_ids, doc_id)
        if doc_id in original_texts:
            del original_texts[doc_id]

    # Add new documents
    for doc_id in added:
        if doc_id in texts_map:
            add_vector_to_index(index, encoder, svd, doc_ids, doc_id, texts_map[doc_id])
            original_texts[doc_id] = texts_map[doc_id]

    # Update modified documents
    for doc_id in modified:
        if doc_id in texts_map:
            # Note: FAISS doesn't support true update, we add new vector
            # Old vector remains but doc_id points to new position
            add_vector_to_index(index, encoder, svd, doc_ids, doc_id, texts_map[doc_id])
            original_texts[doc_id] = texts_map[doc_id]

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
    }


__all__ = [
    "remove_doc",
    "compute_change_ratio",
    "should_full_rebuild",
    "add_vector_to_index",
    "process_incremental_changes",
]