"""
FTS5 工具函数 - FTS5 Utilities

SQLite FTS5 全文搜索工具函数，支持中文分词。

核心功能:
- tokenize_for_fts5: 中文分词预处理（jieba 支持）
- sanitize_fts_query: FTS5 查询清理（防止语法错误和注入）

性能优化:
- LRU 缓存分词结果
- 预编译正则表达式
- 一次性翻译表处理特殊字符

使用:
- SessionDB: FTS5 全文索引
- LongTermArchiveLayer: 归档搜索
"""

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# 检测 jieba 是否可用
try:
    import jieba

    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# LRU 缓存配置
_MAX_CACHE_TEXT_LENGTH = 1000  # 提高缓存阈值，覆盖更多常见查询
_CACHE_MAXSIZE = 2000  # 增加缓存容量，减少重复分词


def tokenize_for_fts5(text: str) -> str:
    """
    中文分词预处理（带缓存）

    - 如果有 jieba，使用 jieba 分词
    - 否则 fallback 到 unicode61（单字符）
    - 使用 LRU 缓存避免重复分词开销
    - 长文本不缓存，避免内存占用过多
    - 空字符串直接返回，避免无意义处理

    Args:
        text: 待分词文本

    Returns:
        分词后的字符串（空格分隔）
    """
    if not text:
        return ""

    # 长文本不缓存，直接分词
    if len(text) > _MAX_CACHE_TEXT_LENGTH:
        if _HAS_JIEBA:
            tokens = jieba.cut(text)
            return " ".join(tokens)
        return text

    # 短文本使用缓存
    return _tokenize_cached(text)


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _tokenize_cached(text: str) -> str:
    """缓存版本的分词函数，仅用于短文本

    Args:
        text: 待分词文本（短文本）

    Returns:
        分词后的字符串
    """
    if _HAS_JIEBA:
        tokens = jieba.cut(text)
        return " ".join(tokens)
    return text


# 预编译翻译表：一次性移除所有 FTS5 特殊字符和 Unicode 特殊字符
# 性能优化：避免循环替换 21 次（11 FTS + 10 Unicode）
_FTS_SPECIAL_CHARS = '"():*^#&|-!~'
_UNICODE_SPECIAL_CHARS = "\u200b\u200c\u200d\u00ad\u2060\u2061\u2062\u2063\u2064\ufeff"
_FTS_SANITIZE_TABLE = str.maketrans("", "", _FTS_SPECIAL_CHARS + _UNICODE_SPECIAL_CHARS)

# 预编译 FTS5 关键字正则表达式
_FTS_KEYWORDS_PATTERN = re.compile(
    r"\b(?:AND|OR|NOT|NEAR|ORDER|BY|LIMIT|OFFSET)\b", flags=re.IGNORECASE
)


def sanitize_fts_query(query: str) -> str:
    """
    清理 FTS5 查询字符串，防止语法错误和注入攻击。

    FTS5 特殊字符: " & | ( ) - : * ^ #
    防护措施:
    1. 分词后移除所有特殊字符（使用 str.translate 一次性处理）
    2. 限制查询长度防止 DoS
    3. 禁止 FTS5 特殊语法（column:, NEAR, NOT, AND, OR）
    4. 仅保留安全的单词匹配
    5. 处理 Unicode 特殊字符

    Args:
        query: 原始查询字符串

    Returns:
        清理后的安全查询字符串
    """
    if not query:
        return ""

    # 限制查询长度防止 DoS
    if len(query) > 200:
        query = query[:200]
        logger.warning("FTS query truncated to 200 chars for security")

    # 分词处理
    if _HAS_JIEBA:
        tokens = jieba.cut(query)
        query = " ".join(tokens)

    # 一次性移除所有特殊字符（性能优化）
    query = query.translate(_FTS_SANITIZE_TABLE)

    # 禁止 FTS5 关键字（预编译正则）
    query = _FTS_KEYWORDS_PATTERN.sub("", query)

    # 移除数字开头的 token（FTS5 可能解析为 column filter）
    tokens = query.split()
    safe_tokens = [
        t for t in tokens if not t.isdigit() and len(t) > 0 and not t[0].isdigit()
    ]
    query = " ".join(safe_tokens)

    return query.strip()


# 公共导出
__all__ = ["_HAS_JIEBA", "sanitize_fts_query", "tokenize_for_fts5"]
