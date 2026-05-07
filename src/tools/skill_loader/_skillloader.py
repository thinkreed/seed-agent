"""
SkillLoader 主类模块

提供渐进式 Skill 加载器核心实现。
"""

import logging
import threading
from pathlib import Path

from ._cache import SkillContentCache
from ._config import (
    CURRENT_PLATFORM,
    MAX_LOADED_SKILL_CACHE,
    MEMORY_GRAPH_CONFIG,
    _ensure_skills_dir,
)
from ._index import build_skills_index
from ._loader import get_gene_slice, load_skill_content, load_skill_ref
from ._matching import compute_match_score, compute_trigger_score, tokenize_query
from ._metadata import convert_lists_to_sets, parse_skill_meta
from ._types import SkillMeta
from .skill_cache import clear_snapshot, load_snapshot, save_snapshot

logger = logging.getLogger(__name__)


class SkillLoader:
    """渐进式 Skill 加载器

    三级披露:
    - Tier 1: 索引 (name + description + triggers)
    - Tier 2: 完整内容
    - Tier 3: 参考文件
    """

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or _ensure_skills_dir()
        self._skills_meta: dict[str, SkillMeta] = {}
        self._lock = threading.Lock()
        self._content_cache = SkillContentCache(max_size=MAX_LOADED_SKILL_CACHE)
        self._platform = CURRENT_PLATFORM
        self._load_metadata()

    def _load_metadata(self) -> None:
        """加载所有 skill 元数据"""
        snapshot = load_snapshot(self.skills_dir)
        if snapshot and snapshot.get("skills"):
            for name, meta in snapshot["skills"].items():
                convert_lists_to_sets(meta)
                self._skills_meta[name] = meta
            return

        self._skills_meta.clear()
        if not self.skills_dir.exists():
            return

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                meta = parse_skill_meta(skill_file, skill_dir)
                if meta:
                    self._skills_meta[meta["name"]] = meta

        save_snapshot(self.skills_dir, self._skills_meta)

    def should_show_skill(self, name: str, available_tools: set[str] | None = None) -> bool:
        """条件激活判断"""
        if name not in self._skills_meta:
            return False

        meta = self._skills_meta[name]
        platforms = meta.get("platforms", [])

        if platforms and not any(
            p.lower() in self._platform.lower() or self._platform.lower() in p.lower() for p in platforms
        ):
            return False

        requires = meta.get("requires_tools", [])
        if requires and available_tools is not None and not all(tool in available_tools for tool in requires):
            return False

        fallback = meta.get("fallback_for_tools", [])
        return not (fallback and available_tools is not None and any(tool in available_tools for tool in fallback))

    def get_skills_prompt(self, available_tools: set[str] | None = None) -> str:
        """生成 Tier 1 索引"""
        return build_skills_index(self._skills_meta, self.should_show_skill, available_tools)

    def match_skill(self, query: str, available_tools: set[str] | None = None) -> str | None:
        """匹配最相关的 skill"""
        query_lower = query.lower()
        query_words = tokenize_query(query)

        best_match, best_score = None, 0.0
        for name, meta in self._skills_meta.items():
            if not self.should_show_skill(name, available_tools):
                continue
            score = compute_match_score(name, meta, query_words, query_lower)
            if score > best_score:
                best_score, best_match = score, name

        return best_match if best_score >= 1.0 else None

    def load_skill_content(self, name: str) -> str | None:
        """加载完整 skill 内容"""
        return load_skill_content(name, self._skills_meta, self._content_cache)

    def get_skill_names(self) -> list[str]:
        """获取所有 skill 名称"""
        return list(self._skills_meta.keys())

    def get_skill_info(self, name: str) -> dict | None:
        """获取 skill 元数据"""
        return self._skills_meta.get(name)

    def load_skill_ref(self, name: str, ref_path: str) -> str | None:
        """加载 skill 的参考文件（Tier 3）"""
        return load_skill_ref(name, ref_path, self._skills_meta)

    def select_best_skill(self, signals: list[str], available_tools: set[str] | None = None) -> str | None:
        """Memory Graph 增强的 Skill 选择"""
        if not MEMORY_GRAPH_CONFIG.get("enabled", True):
            return self.match_skill(" ".join(signals) if signals else "", available_tools)

        candidates = [n for n in self._skills_meta if self.should_show_skill(n, available_tools)]
        if not candidates:
            return None

        scores = {n: compute_trigger_score(n, signals, self._skills_meta) for n in candidates}
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[0][0] if ranked else None

    def get_gene_slice(self, name: str) -> str | None:
        """提取 Gene slice (Tier 2a): 核心控制信号"""
        return get_gene_slice(name, self._skills_meta)

    def refresh(self) -> None:
        """刷新元数据"""
        with self._lock:
            self._content_cache.clear()
        clear_snapshot()
        self._skills_meta.clear()
        self._load_metadata()


__all__ = ["SkillLoader"]