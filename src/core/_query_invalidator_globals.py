"""
QueryInvalidator 全局实例和辅助函数
"""

from ._query_invalidator import QueryInvalidator

# 全局实例
_query_invalidator: QueryInvalidator | None = None


def get_query_invalidator() -> QueryInvalidator:
    """获取全局 QueryInvalidator 实例"""
    global _query_invalidator
    if _query_invalidator is None:
        _query_invalidator = QueryInvalidator()
    return _query_invalidator


def setup_default_entities() -> None:
    """设置默认实体关联"""
    invalidator = get_query_invalidator()
    invalidator.register("memory", ["memory:search:*", "memory:list", "memory:detail:*"])
    invalidator.register("session", ["session:list", "session:detail:*", "session:events:*"])
    invalidator.register("tool", ["tool:list", "tool:detail:*", "tool:execute:*"])
    invalidator.register("llm", ["llm:call:*", "llm:stream:*", "llm:stats"])
    invalidator.register("autonomous", ["autonomous:status", "autonomous:history"])


__all__ = [
    "get_query_invalidator",
    "setup_default_entities",
]