"""记忆去重逻辑

Wiki 知识落地 P2 (MIA): 记忆去重阈值

相似度 ≥ 0.9999 时执行去重逻辑：
- 现有记忆错误 + 新记忆正确 → 替换
- 都正确 → 保留更短版本
"""

import os

DEDUPLICATION_THRESHOLD = 0.9999  # 相似度阈值


def _compute_similarity(text1: str, text2: str) -> float:
    """计算文本相似度（简化版 TF-IDF 余弦相似度）

    Args:
        text1: 文本1
        text2: 文本2

    Returns:
        相似度分数 [0.0, 1.0]
    """
    if not text1 or not text2:
        return 0.0

    # 简化的关键词提取（词频统计）
    words1 = text1.lower().split()
    words2 = text2.lower().split()

    # 去除常见停用词
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                 "have", "has", "had", "do", "does", "did", "will", "would", "could",
                 "should", "may", "might", "must", "shall", "can", "need", "dare",
                 "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
                 "from", "as", "into", "through", "during", "before", "after",
                 "above", "below", "between", "under", "again", "further", "then",
                 "once", "here", "there", "when", "where", "why", "how", "all", "each",
                 "few", "more", "most", "other", "some", "such", "no", "nor", "not",
                 "only", "own", "same", "so", "than", "too", "very", "just", "and",
                 "but", "if", "or", "because", "until", "while", "although", "though",
                 "的", "是", "在", "有", "和", "与", "或", "但", "如果", "因为", "所以",
                 "这", "那", "一个", "这个", "那个", "之", "了", "着", "过"}

    words1 = [w for w in words1 if w not in stopwords and len(w) > 1]
    words2 = [w for w in words2 if w not in stopwords and len(w) > 1]

    if not words1 or not words2:
        return 0.0

    # 计算词频
    freq1 = {}
    freq2 = {}
    for w in words1:
        freq1[w] = freq1.get(w, 0) + 1
    for w in words2:
        freq2[w] = freq2.get(w, 0) + 1

    # 计算交集和余弦相似度
    intersection = set(freq1.keys()) & set(freq2.keys())
    if not intersection:
        return 0.0

    dot_product = sum(freq1[w] * freq2[w] for w in intersection)
    norm1 = sum(v ** 2 for v in freq1.values()) ** 0.5
    norm2 = sum(v ** 2 for v in freq2.values()) ** 0.5

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def _check_existing_memory(path: str, content: str, metadata: str = "") -> str | None:
    """检查是否存在相似记忆，返回去重决策

    MIA 记忆去重逻辑：
    - 相似度 ≥ 0.9999 时执行去重
    - 现有记忆错误 + 新记忆正确 → 替换
    - 都正确 → 保留更短版本
    - 无相似记忆 → 允许写入

    Args:
        path: 目标路径
        content: 新内容
        metadata: 元数据（包含验证状态）

    Returns:
        None: 允许写入
        str: 去重决策消息（阻止写入或建议替换）
    """
    if not os.path.exists(path):
        return None  # 文件不存在，允许写入

    try:
        with open(path, encoding="utf-8") as f:
            existing_content = f.read()
    except Exception:
        return None  # 无法读取，允许写入

    # 计算相似度
    similarity = _compute_similarity(existing_content, content)

    if similarity < DEDUPLICATION_THRESHOLD:
        return None  # 相似度低于阈值，允许写入

    # 检查验证状态（从 metadata 提取）
    existing_verified = "verified=true" in existing_content.lower() or "tool_call_success" in existing_content
    new_verified = "verified=true" in metadata.lower() or metadata == ""

    # MIA 去重逻辑
    if not existing_verified and new_verified:
        # 现有记忆错误，新记忆正确 → 替换
        return f"REPLACE: Existing memory has lower verification (similarity={similarity:.4f})"

    if existing_verified and new_verified:
        # 都正确 → 保留更短版本
        existing_len = len(existing_content.strip())
        new_len = len(content.strip())
        if new_len < existing_len:
            return f"REPLACE: New content is shorter (similarity={similarity:.4f})"
        else:
            return f"SKIP: Existing content is shorter/better (similarity={similarity:.4f})"

    # 现有记忆正确，新记忆未验证 → 保留现有
    return f"SKIP: Existing memory is verified, new is not (similarity={similarity:.4f})"


__all__ = [
    "DEDUPLICATION_THRESHOLD",
    "_check_existing_memory",
    "_compute_similarity",
]