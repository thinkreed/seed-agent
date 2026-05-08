"""SemanticIndex incremental update: <30% incremental, >=30% full rebuild."""

import logging
import numpy as np

logger = logging.getLogger("seed_agent")


def remove_doc(doc_ids: list[str], doc_id: str) -> bool:
    """Remove document from index."""
    if doc_id in doc_ids:
        doc_ids.remove(doc_id)
        return True
    return False


def compute_change_ratio(added: list[str], removed: list[str], modified: list[str], total_docs: int) -> float:
    """Compute ratio of changes to total documents."""
    total_changes = len(added) + len(removed) + len(modified)
    if total_docs == 0:
        return 1.0 if total_changes > 0 else 0.0
    return total_changes / total_docs


def should_full_rebuild(added: list[str], removed: list[str], modified: list[str], total_docs: int, threshold: float = 0.3) -> bool:
    """Decide whether to full rebuild vs incremental update."""
    return compute_change_ratio(added, removed, modified, total_docs) >= threshold


def add_vector_to_index(index, encoder, svd, doc_ids: list[str], doc_id: str, text: str) -> None:
    """Add a single vector to existing index."""
    if index is None:
        return
    vec = encoder.transform(text).astype(np.float32)
    if svd is not None:
        vec = svd.transform(vec).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
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
    index, encoder, svd, doc_ids: list[str], changes: dict[str, list[str]], texts_map: dict[str, str], original_texts: dict[str, str]
) -> dict[str, list[str]]:
    """Process incremental changes without full rebuild."""
    added, removed, modified = changes.get("added", []), changes.get("removed", []), changes.get("modified", [])
    for doc_id in removed:
        remove_doc(doc_ids, doc_id)
        original_texts.pop(doc_id, None)
    for doc_id in added:
        if doc_id in texts_map:
            add_vector_to_index(index, encoder, svd, doc_ids, doc_id, texts_map[doc_id])
            original_texts[doc_id] = texts_map[doc_id]
    for doc_id in modified:
        if doc_id in texts_map:
            add_vector_to_index(index, encoder, svd, doc_ids, doc_id, texts_map[doc_id])
            original_texts[doc_id] = texts_map[doc_id]
    return {"added": added, "removed": removed, "modified": modified}


def prepare_incremental_changes(pending_updates: dict[str, str] | None) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Prepare changes dict from pending updates."""
    if not pending_updates:
        return {}, {}
    return {"added": [], "removed": [], "modified": list(pending_updates.keys())}, pending_updates.copy()


__all__ = ["remove_doc", "compute_change_ratio", "should_full_rebuild", "add_vector_to_index", "process_incremental_changes", "prepare_incremental_changes"]