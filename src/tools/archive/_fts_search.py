"""
FTS5 全文搜索实现

基于 Hermes Agent FTS5 设计：
- jieba 中文分词
- 安全查询字符串处理
- 搜索结果提取和匹配片段

核心功能：
- sanitize_fts_query: 安全化 FTS5 查询字符串
- tokenize_for_fts5: 中文分词预处理
- search_with_context: 语义搜索 + 摘要提取
"""

import logging
from typing import Any

from src.tools.fts_utils import sanitize_fts_query

logger = logging.getLogger(__name__)


def tokenize_for_fts5(text: str) -> str:
    """使用 jieba 分词预处理文本用于 FTS5

    Args:
        text: 原始文本

    Returns:
        分词后的文本（空格分隔）
    """
    if not text or not text.strip():
        return ""

    try:
        import jieba

        # 使用精确模式分词
        tokens = jieba.lcut(text)
        return " ".join(tokens)
    except ImportError:
        # jieba 未安装，使用简单空格分隔
        logger.debug("jieba not installed, using simple tokenization")
        return text


def extract_matched_snippet(content: str, keyword: str) -> str:
    """提取匹配片段

    Args:
        content: 内容文本
        keyword: 关键词

    Returns:
        包含关键词的片段
    """
    if not content:
        return ""

    keyword_lower = keyword.lower()
    content_lower = content.lower()

    idx = content_lower.find(keyword_lower)
    if idx >= 0:
        start = max(0, idx - 50)
        end = min(len(content), idx + len(keyword) + 50)
        return content[start:end]

    return content[:100]


def search_with_context(
    conn: Any,
    keyword: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """语义搜索 + 摘要提取

    Args:
        conn: 数据库连接
        keyword: 搜索关键词
        limit: 结果限制

    Returns:
        [{
            "archive_id": "...",
            "session_id": "...",
            "summary": "核心结论摘要",
            "matched_snippet": "匹配片段",
            "key_findings": ["发现1", "发现2"],
            "timestamp": "...",
            "relevance_score": 0.XX
        }]
    """
    import json

    # FTS5 搜索
    fts_query = sanitize_fts_query(keyword)
    if not fts_query:
        return []

    try:
        rows = conn.execute(
            """
            SELECT
                a.archive_id,
                a.session_id,
                a.summary,
                a.key_findings,
                a.created_at,
                fts.event_content as matched_content
            FROM archives a
            JOIN archives_fts fts ON a.archive_id = fts.archive_id
            WHERE archives_fts MATCH ?
            ORDER BY a.created_at DESC
            LIMIT ?
        """,
            (fts_query, limit),
        ).fetchall()

        results = []
        for row in rows:
            key_findings = json.loads(row["key_findings"] or "[]")
            matched_snippet = extract_matched_snippet(
                row["matched_content"] or "", keyword
            )

            results.append(
                {
                    "archive_id": row["archive_id"],
                    "session_id": row["session_id"],
                    "summary": row["summary"],
                    "matched_snippet": matched_snippet,
                    "key_findings": key_findings,
                    "timestamp": row["created_at"],
                    "relevance_score": 1.0,  # FTS5 不返回分数
                }
            )

        return results
    except Exception as e:
        logger.warning(f"FTS search failed: {type(e).__name__}: {e}")
        return []


def search_by_time_range(
    conn: Any,
    start_time: str,
    end_time: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """时间范围搜索

    Args:
        conn: 数据库连接
        start_time: ISO 格式开始时间
        end_time: ISO 格式结束时间
        limit: 结果限制

    Returns:
        归档列表
    """
    import json

    rows = conn.execute(
        """
        SELECT archive_id, session_id, summary, key_findings, created_at, events_count
        FROM archives
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at DESC
        LIMIT ?
    """,
        (start_time, end_time, limit),
    ).fetchall()

    return [
        {
            "archive_id": row["archive_id"],
            "session_id": row["session_id"],
            "summary": row["summary"],
            "key_findings": json.loads(row["key_findings"] or "[]"),
            "timestamp": row["created_at"],
            "events_count": row["events_count"],
        }
        for row in rows
    ]