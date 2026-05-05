"""
渐进式 Skill 加载器

核心优化:
1. 两级缓存 (进程内 LRU + 磁盘快照)
2. 条件激活 (requires_tools, fallback_for, platforms)
3. Prompt Injection 安全扫描
4. 分类分组索引
5. 三级渐进式披露: 索引(Tier1) → 内容(Tier2) → 参考文件(Tier3)

架构拆分:
- _config.py: 配置和常量
- 主类 SkillLoader 在此文件中

使用方法:
    from src.tools.skill_loader import SkillLoader, load_skill
    
    loader = SkillLoader()
    content = loader.load_skill_content("my-skill")
"""

import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ._config import (
    _RE_CN_WORD,
    _RE_EN_WORD,
    _RE_EN_WORD_HYPHEN,
    CURRENT_PLATFORM,
    MAX_LOADED_SKILL_CACHE,
    MEMORY_GRAPH_CONFIG,
    PLATFORM_MAP,
    _ensure_skills_dir,
)
from .skill_cache import (
    SNAPSHOT_PATH,
    _build_manifest,
    build_manifest,
    clear_snapshot,
    load_snapshot,
    save_snapshot,
)
from .skill_security import (
    INJECTION_PATTERNS,
    _scan_for_injections,
    _validate_skill_structure,
    scan_for_injections,
    validate_skill_structure,
    validate_path_within_dir,
)

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)


class SkillMeta(dict):
    """Skill 元数据类型
    
    包含: path, dir, name, description, category, version, triggers, platforms 等
    """
    pass


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
        self._content_cache: OrderedDict[str, str] = OrderedDict()
        self._platform = CURRENT_PLATFORM
        self._load_metadata()

    def _load_metadata(self) -> None:
        """加载所有 skill 元数据"""
        snapshot = load_snapshot(self.skills_dir)
        if snapshot and snapshot.get("skills"):
            for name, meta in snapshot["skills"].items():
                if "triggers_lower" in meta and isinstance(meta["triggers_lower"], list):
                    meta["triggers_lower"] = set(meta["triggers_lower"])
                if "desc_words" in meta and isinstance(meta["desc_words"], list):
                    meta["desc_words"] = set(meta["desc_words"])
                self._skills_meta[name] = meta
            return

        self._skills_meta.clear()
        if not self.skills_dir.exists():
            return

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                meta = self._parse_frontmatter(skill_file)
                if not meta or "name" not in meta:
                    continue

                triggers = self._normalize_triggers(meta.get("triggers", []))
                metadata = meta.get("metadata", {}) or {}

                self._skills_meta[meta["name"]] = {
                    "path": str(skill_file),
                    "dir": str(skill_dir),
                    "name": meta["name"],
                    "description": meta.get("description", "")[:300],
                    "category": meta.get("category", "general"),
                    "version": meta.get("version", "1.0"),
                    "triggers": triggers,
                    "triggers_lower": {t.lower() for t in triggers},
                    "platforms": self._normalize_str_list(meta.get("platforms", [])),
                    "allowed_tools": meta.get("allowed-tools", ""),
                    "requires_tools": self._normalize_str_list(metadata.get("requires_tools", [])),
                    "fallback_for_tools": self._normalize_str_list(metadata.get("fallback_for_tools", [])),
                }

                desc = self._skills_meta[meta["name"]]["description"]
                desc_lower = desc.lower()
                desc_words = set(_RE_EN_WORD.findall(desc_lower))
                desc_words.update(_RE_CN_WORD.findall(desc_lower))
                self._skills_meta[meta["name"]]["desc_words"] = desc_words
            except Exception as e:
                logger.debug(f"Failed to parse skill: {type(e).__name__}")
                continue

        save_snapshot(self.skills_dir, self._skills_meta)

    def _parse_frontmatter(self, skill_file: Path) -> dict | None:
        """解析 YAML frontmatter"""
        try:
            with open(skill_file, encoding="utf-8") as f:
                content = f.read()
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            return yaml.safe_load(parts[1].strip())
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            return None

    def _normalize_triggers(self, triggers: str | list[Any] | None) -> list[str]:
        """规范化 triggers"""
        if isinstance(triggers, str):
            return self._normalize_str_list(triggers)
        if isinstance(triggers, list):
            return self._flatten_triggers(triggers)
        return []

    def _flatten_triggers(self, triggers: list) -> list[str]:
        """扁平化嵌套列表"""
        result = []
        for item in triggers:
            if isinstance(item, str):
                result.append(item.strip())
            elif isinstance(item, list):
                result.extend(self._flatten_triggers(item))
        return result

    def _normalize_str_list(self, value) -> list[str]:
        """规范化字符串或列表"""
        if isinstance(value, str):
            return [t.strip() for t in value.split(",") if t.strip()]
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def should_show_skill(self, name: str, available_tools: set[str] | None = None) -> bool:
        """条件激活判断"""
        if name not in self._skills_meta:
            return False

        meta = self._skills_meta[name]

        platforms = meta.get("platforms", [])
        if platforms and not any(
            p.lower() in self._platform.lower() or self._platform.lower() in p.lower()
            for p in platforms
        ):
            return False

        requires = meta.get("requires_tools", [])
        if requires and available_tools is not None and not all(tool in available_tools for tool in requires):
            return False

        fallback = meta.get("fallback_for_tools", [])
        return not (fallback and available_tools is not None and any(tool in available_tools for tool in fallback))

    def get_skills_prompt(self, available_tools: set[str] | None = None) -> str:
        """生成 Tier 1 索引"""
        visible_skills = {
            name: meta for name, meta in self._skills_meta.items()
            if self.should_show_skill(name, available_tools)
        }
        if not visible_skills:
            return ""

        categories: dict[str, list[dict]] = {}
        for meta in visible_skills.values():
            cat = meta.get("category", "general")
            categories.setdefault(cat, []).append(meta)

        lines = ["<skills_index>", "## 可用技能", "", "触发词匹配时调用 `load_skill` 加载完整指令。", ""]
        
        if "general" in categories:
            lines.extend(self._render_category("general", categories.pop("general")))
        
        for cat, skills in sorted(categories.items()):
            lines.extend(self._render_category(cat, skills, indent=True))

        lines.append("</skills_index>")
        return "\n".join(lines)

    def _render_category(self, cat: str, skills: list[dict], indent: bool = False) -> list[str]:
        """渲染分类区块"""
        prefix = "  - " if indent else "- "
        lines = [f"<category name='{cat}'>"]
        for meta in skills:
            desc = meta["description"][:150]
            lines.append(f"{prefix}**{meta['name']}**: {desc}")
        lines.extend(["</category>", ""])
        return lines

    def match_skill(self, query: str, available_tools: set[str] | None = None) -> str | None:
        """匹配最相关的 skill"""
        query_lower = query.lower()
        query_words = self._tokenize_query(query)

        best_match = None
        best_score = 0.0

        for name, meta in self._skills_meta.items():
            if not self.should_show_skill(name, available_tools):
                continue

            score = self._compute_match_score(name, meta, query_words, query_lower)
            if score > best_score:
                best_score = score
                best_match = name

        return best_match if best_score >= 1.0 else None

    def _tokenize_query(self, query: str) -> list[str]:
        """分词"""
        query_lower = query.lower()
        en_words = _RE_EN_WORD_HYPHEN.findall(query_lower)
        cn_words = _RE_CN_WORD.findall(query_lower)
        return en_words + cn_words or [query_lower]

    def _compute_match_score(self, name: str, meta: SkillMeta, query_words: list[str], query_lower: str) -> float:
        """计算匹配分数"""
        score = 0.0

        name_lower = name.lower()
        if name_lower == query_lower:
            score += 3.0
        elif name_lower in query_lower or query_lower in name_lower:
            score += 2.0

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

        if not trigger_matched:
            desc_words = meta.get("desc_words", set())
            for qw in query_words:
                if any(qw in dw or dw in qw for dw in desc_words):
                    score += 0.5

        return score

    def load_skill_content(self, name: str) -> str | None:
        """加载完整 skill 内容"""
        with self._lock:
            if name in self._content_cache:
                self._content_cache.move_to_end(name)
                return self._content_cache[name]

        if name not in self._skills_meta:
            return None

        skill_dir = Path(self._skills_meta[name]["dir"])
        skill_file = Path(self._skills_meta[name]["path"])

        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        # 安全检查
        injection = scan_for_injections(content)
        if injection:
            return f"[Security Error] Skill '{name}' blocked: {injection}"

        symlink_check = validate_skill_structure(skill_dir)
        if symlink_check:
            return f"[Security Error] {symlink_check}"

        # 路径展开
        try:
            from src.shared_config import get_paths_config
            seed_dir_str = str(get_paths_config().seed_base)
            content = content.replace("~/.seed", seed_dir_str)
            home_dir = os.path.expanduser("~")
            content = content.replace("~", home_dir)
        except RuntimeError:
            pass

        fenced_content = f"<skill_content name='{name}'>\n{content}\n</skill_content>"

        with self._lock:
            if len(self._content_cache) >= MAX_LOADED_SKILL_CACHE:
                self._content_cache.popitem(last=False)
            self._content_cache[name] = fenced_content

        return fenced_content

    def get_skill_names(self) -> list[str]:
        """获取所有 skill 名称"""
        return list(self._skills_meta.keys())

    def get_skill_info(self, name: str) -> dict | None:
        """获取 skill 元数据"""
        return self._skills_meta.get(name)

    def load_skill_ref(self, name: str, ref_path: str) -> str | None:
        """加载 skill 的参考文件（Tier 3）"""
        if name not in self._skills_meta:
            return None

        skill_dir = Path(self._skills_meta[name]["dir"])

        if ".." in ref_path:
            return "Error: Path traversal not allowed."

        target = (skill_dir / ref_path).resolve()
        if not validate_path_within_dir(target, skill_dir):
            return "Error: Path escapes skill directory."

        if not target.exists() or not target.is_file():
            return f"Reference file not found: {ref_path}"

        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"Error reading reference: {e}"

    def select_best_skill(self, signals: list[str], available_tools: set[str] | None = None) -> str | None:
        """Memory Graph 增强的 Skill 选择"""
        if not MEMORY_GRAPH_CONFIG.get("enabled", True):
            query = " ".join(signals) if signals else ""
            return self.match_skill(query, available_tools)

        candidates = [
            name for name in self._skills_meta
            if self.should_show_skill(name, available_tools)
        ]
        if not candidates:
            return None

        # 简单排序（按触发分数）
        scores = {}
        for skill_name in candidates:
            scores[skill_name] = self._compute_trigger_score(skill_name, signals)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        return ranked[0][0] if ranked else None

    def _compute_trigger_score(self, skill_name: str, signals: list[str]) -> float:
        """计算触发器匹配分数"""
        if not signals:
            return 0.0

        meta = self._skills_meta.get(skill_name)
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

    def get_gene_slice(self, name: str) -> str | None:
        """提取 Gene slice (Tier 2a): 核心控制信号"""
        if name not in self._skills_meta:
            return None

        skill_file = Path(self._skills_meta[name]["path"])
        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        # 解析 YAML frontmatter
        if not content.startswith("---"):
            return f"[SYSTEM: Skill '{name}' activated]\n\n{content[:500]}"

        parts = content.split("---", 2)
        if len(parts) < 3:
            return f"[SYSTEM: Skill '{name}' activated]\n\n{content[:500]}"

        try:
            import yaml
            frontmatter = yaml.safe_load(parts[1].strip())
            
            output = f"[SYSTEM: Skill '{name}' activated]\n\n"
            
            # 提取 strategy 字段
            if "strategy" in frontmatter:
                output += "## Strategy\n"
                for item in frontmatter["strategy"]:
                    output += f"- {item}\n"
            
            # 提取 avoid 字段
            if "avoid" in frontmatter:
                output += "\n## AVOID\n"
                for item in frontmatter["avoid"]:
                    output += f"- {item}\n"
            
            # 提取 constraints 字段
            if "constraints" in frontmatter:
                output += "\n## Constraints\n"
                constraints = frontmatter["constraints"]
                if isinstance(constraints, dict):
                    for k, v in constraints.items():
                        output += f"- {k}: {v}\n"
                elif isinstance(constraints, list):
                    for c in constraints:
                        output += f"- {c}\n"
            
            # 提取 validation 字段
            if "validation" in frontmatter:
                output += "\n## Validation\n"
                for item in frontmatter["validation"]:
                    output += f"- {item}\n"
            
            return output if len(output) > 50 else f"[SYSTEM: Skill '{name}' activated]\n\n{content[:500]}"
        except Exception:
            return f"[SYSTEM: Skill '{name}' activated]\n\n{content[:500]}"

    def refresh(self) -> None:
        """刷新元数据"""
        with self._lock:
            self._content_cache.clear()
        clear_snapshot()
        self._skills_meta.clear()
        self._load_metadata()


# === 全局单例 ===

_global_loader: SkillLoader | None = None
_loader_lock = threading.Lock()


def get_loader() -> SkillLoader:
    """获取全局 loader"""
    global _global_loader
    if _global_loader is None:
        with _loader_lock:
            if _global_loader is None:
                _global_loader = SkillLoader()
    return _global_loader


def load_skill(name: str) -> str:
    """加载 skill 内容"""
    loader = get_loader()
    content = loader.load_skill_content(name)
    if content:
        return f'[SYSTEM: Skill "{name}" activated]\n\n{content}'
    return f"Skill not found: {name}. Available: {', '.join(loader.get_skill_names())}"


def list_skills() -> str:
    """列出所有 skills"""
    loader = get_loader()
    skills = list(loader._skills_meta.values())

    if not skills:
        return "No skills available."

    categories: dict[str, list[dict]] = {}
    for s in skills:
        cat = s.get("category", "general")
        categories.setdefault(cat, []).append(s)

    output = "Available Skills:\n"
    for cat, items in sorted(categories.items()):
        output += f"\n  [{cat}]\n"
        for s in items:
            desc = s.get("description", "")[:100]
            output += f"  - {s['name']}: {desc}\n"

    return output


def search_skill(query: str) -> str:
    """搜索 skill"""
    loader = get_loader()
    match = loader.match_skill(query)

    if match:
        content = loader.load_skill_content(match)
        if content:
            return f"[Matched] {match}\n\n{content}"

    candidates = []
    query_lower = query.lower()
    for name, meta in loader._skills_meta.items():
        if query_lower in name.lower() or query_lower in meta["description"].lower():
            candidates.append(f"- {name}: {meta['description'][:100]}")

    if candidates:
        return "No exact match. Candidates:\n" + "\n".join(candidates)
    return f"No skill matches: {query}"


def register_skill_tools(registry: "ToolRegistry") -> None:
    """注册 skill 工具"""
    registry.register("load_skill", load_skill)
    registry.register("list_skills", list_skills)
    registry.register("search_skill", search_skill)


# 兼容性别名
_get_loader = get_loader


__all__ = [
    "SkillLoader",
    "get_loader",
    "_get_loader",
    "list_skills",
    "load_skill",
    "register_skill_tools",
    "search_skill",
    # 导出子模块内容以保持向后兼容
    "MEMORY_GRAPH_CONFIG",
    "PLATFORM_MAP",
    "SNAPSHOT_PATH",
    "_build_manifest",
    "build_manifest",
    "clear_snapshot",
    "load_snapshot",
    "save_snapshot",
    "INJECTION_PATTERNS",
    "_scan_for_injections",
    "_validate_skill_structure",
    "scan_for_injections",
    "validate_skill_structure",
]