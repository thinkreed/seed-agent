"""
Skill 匹配模块

提供 Skill 查询匹配和评分功能。
"""

from ._config import _RE_CN_WORD, _RE_EN_WORD, _RE_EN_WORD_HYPHEN
from ._types import SkillMeta


def tokenize_query(query: str) -> list[str]:
    """分词

    Args:
        query: 查询字符串

    Returns:
        分词后的词列表
    """
    query_lower = query.lower()
    en_words = _RE_EN_WORD_HYPHEN.findall(query_lower)
    cn_words = _RE_CN_WORD.findall(query_lower)
    return en_words + cn_words or [query_lower]


def compute_match_score(
    name: str,
    meta: SkillMeta,
    query_words: list[str],
    query_lower: str,
) -> float:
    """计算匹配分数

    Args:
        name: Skill 名称
        meta: Skill 元数据
        query_words: 分词后的查询词
        query_lower: 小写查询字符串

    Returns:
        匹配分数
    """
    score = 0.0

    # 名称匹配
    name_lower = name.lower()
    if name_lower == query_lower:
        score += 3.0
    elif name_lower in query_lower or query_lower in name_lower:
        score += 2.0

    # 触发词匹配
    triggers_lower = meta.get("triggers_lower", set())
    trigger_matched = False

    for qw in query_words:
        if qw in triggers_lower:
            score += 3.0
            trigger_matched = True
        else:
            for trigger_lower in triggers_lower:
                if qw in trigger_lower or trigger_lower in qw:
                    score += 1.0
                    trigger_matched = True

    # 描述词匹配
    if not trigger_matched:
        desc_words = meta.get("desc_words", set())
        for qw in query_words:
            if any(qw in dw or dw in qw for dw in desc_words):
                score += 0.5

    return score


def compute_trigger_score(skill_name: str, signals: list[str], skills_meta: dict) -> float:
    """计算触发器匹配分数

    Args:
        skill_name: Skill 名称
        signals: 信号列表
        skills_meta: Skill 元数据字典

    Returns:
        触发器匹配分数 (最大 3.0)
    """
    if not signals:
        return 0.0

    meta = skills_meta.get(skill_name)
    if not meta:
        return 0.0

    triggers_lower = meta.get("triggers_lower", set())
    if not triggers_lower:
        return 0.0

    signals_lower = [s.lower() for s in signals]
    score = 0.0
    for signal_lower in signals_lower:
        if signal_lower in triggers_lower:
            score += 1.0
        else:
            for trigger_lower in triggers_lower:
                if signal_lower in trigger_lower or trigger_lower in signal_lower:
                    score += 0.5
    return min(score, 3.0)


def extract_desc_words(description: str) -> set[str]:
    """从描述中提取词

    Args:
        description: 描述文本

    Returns:
        词集合
    """
    desc_lower = description.lower()
    desc_words = set(_RE_EN_WORD.findall(desc_lower))
    desc_words.update(_RE_CN_WORD.findall(desc_lower))
    return desc_words


__all__ = [
    "tokenize_query",
    "compute_match_score",
    "compute_trigger_score",
    "extract_desc_words",
]