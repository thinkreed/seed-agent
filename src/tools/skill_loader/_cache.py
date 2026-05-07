"""
Skill 内容缓存模块

提供进程内 LRU 缓存，用于缓存已加载的 Skill 内容。
"""

import threading
from collections import OrderedDict


class SkillContentCache:
    """Skill 内容的 LRU 缓存

    线程安全的 LRU 缓存实现，用于存储已加载的 Skill 内容。
    """

    def __init__(self, max_size: int = 5):
        """初始化缓存

        Args:
            max_size: 最大缓存条目数
        """
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, name: str) -> str | None:
        """获取缓存内容

        如果命中缓存，自动将条目移到末尾（LRU 更新）。

        Args:
            name: Skill 名称

        Returns:
            缓存的内容，未命中返回 None
        """
        with self._lock:
            if name in self._cache:
                self._cache.move_to_end(name)
                return self._cache[name]
            return None

    def set(self, name: str, content: str) -> None:
        """设置缓存内容

        如果缓存已满，移除最旧的条目。

        Args:
            name: Skill 名称
            content: Skill 内容
        """
        with self._lock:
            if name in self._cache:
                self._cache.move_to_end(name)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
            self._cache[name] = content

    def contains(self, name: str) -> bool:
        """检查缓存是否包含指定 Skill

        Args:
            name: Skill 名称

        Returns:
            是否包含该 Skill
        """
        with self._lock:
            return name in self._cache

    def get_cached(self, name: str) -> tuple[bool, str | None]:
        """获取缓存内容并返回是否命中

        原子操作，避免竞态条件。

        Args:
            name: Skill 名称

        Returns:
            (是否命中, 内容) 元组
        """
        with self._lock:
            if name in self._cache:
                self._cache.move_to_end(name)
                return True, self._cache[name]
            return False, None

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """获取当前缓存大小

        Returns:
            缓存条目数
        """
        with self._lock:
            return len(self._cache)

    def keys(self) -> list[str]:
        """获取所有缓存的 Skill 名称

        Returns:
            Skill 名称列表
        """
        with self._lock:
            return list(self._cache.keys())

    def __contains__(self, name: str) -> bool:
        """支持 `in` 操作符

        Args:
            name: Skill 名称

        Returns:
            是否包含该 Skill
        """
        with self._lock:
            return name in self._cache

    def __len__(self) -> int:
        """支持 len() 操作

        Returns:
            缓存大小
        """
        with self._lock:
            return len(self._cache)


__all__ = [
    "SkillContentCache",
]