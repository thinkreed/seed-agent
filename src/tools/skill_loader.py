"""
渐进式 Skill 加载器 - 参考 Hermes Agent 渐进式披露架构

核心优化:
1. 两级缓存 (进程内 LRU + 磁盘快照)
2. 条件激活 (requires_tools, fallback_for, platforms)
3. Prompt Injection 安全扫描
4. 分类分组索引 (按 category/platforms 分组)
5. 三级渐进式披露: 索引(Tier1) → 内容(Tier2) → 参考文件(Tier3)

Memory Graph 增强:
6. 基于历史结果的选择算法 (Laplace平滑 + 指数衰减)
7. 低价值策略禁用机制 (ban threshold)
8. 冷启动处理 + 近期成功加成
9. Gene slice 提取 (Tier 2a: strategy + avoid + constraints)

Token 节约估算:
- 全量加载: ~8700 tokens (12 skills)
- 索引模式:   ~300 tokens  (96.6% 节约)
- Gene slice: ~230 tokens  (97.4% 节约)
"""

import difflib
import logging
import os
import re
import sys
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Set, TypedDict

import yaml  # type: ignore[import-untyped]

# 尝试导入共享配置模块（在顶部导入避免 E402）
try:
    from src.shared_config import get_memory_graph_config
    _HAS_SHARED_CONFIG = True
except ImportError:
    _HAS_SHARED_CONFIG = False

from .skill_cache import (
    SNAPSHOT_PATH,
    build_manifest,
    clear_snapshot,
    load_snapshot,
    save_snapshot,
)
from .skill_security import (
    INJECTION_PATTERNS,
    scan_for_injections,
    validate_path_within_dir,
    validate_skill_structure,
)

logger = logging.getLogger(__name__)

# 兼容性导出：保持原有私有函数名可用
_build_manifest = build_manifest
_scan_for_injections = scan_for_injections
_validate_skill_structure = validate_skill_structure


class SkillMeta(TypedDict, total=False):
    """Skill 元数据类型定义"""
    path: str
    dir: str
    name: str
    description: str
    category: str
    version: str
    triggers: list[str]
    triggers_lower: set[str]
    platforms: list[str]
    allowed_tools: str
    requires_tools: list[str]
    fallback_for_tools: list[str]
    desc_words: set[str]

# 显式导出列表（用于向后兼容和避免 ruff F401 警告）
__all__ = [
    "INJECTION_PATTERNS",
    "MEMORY_GRAPH_CONFIG",
    "PLATFORM_MAP",
    "SKILLS_DIR",
    "SNAPSHOT_PATH",
    "SkillLoader",
    "_build_manifest",
    "_get_loader",
    "_scan_for_injections",
    "_validate_skill_structure",
    "build_manifest",
    "clear_snapshot",
    "get_loader",
    "list_skills",
    "load_skill",
    "load_snapshot",
    "save_snapshot",
    "scan_for_injections",
    "search_skill",
    "validate_path_within_dir",
    "validate_skill_structure",
]

# ==================== 常量配置 ====================

SKILLS_DIR = Path(os.path.expanduser("~")) / ".seed" / "memory" / "skills"

# LRU 缓存配置
MAX_LOADED_SKILL_CACHE = 5  # 最多缓存 5 个已加载的完整 skill 内容

# 内容截取限制
MAX_COMPACT_CONTENT = 500  # 精简版 skill 内容最大字符数

# 平台映射
PLATFORM_MAP = {
    "win32": "windows",
    "linux": "linux",
    "darwin": "macos",
    "windows": "windows",
    "macos": "macos",
}

# 使用共享配置模块
if _HAS_SHARED_CONFIG:
    _mg_config = get_memory_graph_config()
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": _mg_config.half_life_days,
        "ban_threshold": _mg_config.ban_threshold,
        "min_attempts_for_ban": _mg_config.min_attempts_for_ban,
        "memory_weight": _mg_config.memory_weight,
        "trigger_weight": _mg_config.trigger_weight,
        "cold_start_penalty": _mg_config.cold_start_penalty,
        "recent_boost_factor": _mg_config.recent_boost_factor,
        "recent_days": _mg_config.recent_days,
        "enabled": True,  # Memory Graph 选择默认启用
    }
else:
    # Fallback: 使用默认值（避免循环导入问题）
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": 30,
        "ban_threshold": 0.18,
        "min_attempts_for_ban": 2,
        "memory_weight": 0.6,
        "trigger_weight": 0.4,
        "cold_start_penalty": 0.5,
        "recent_boost_factor": 0.2,
        "recent_days": 30,
        "enabled": True,
    }


# ==================== SkillLoader 核心类 ====================

class SkillLoader:
    """
    渐进式 Skill 加载器

    三级披露:
    - Tier 1: 索引 (name + description + triggers) - 注入 System Prompt
    - Tier 2: 完整内容 - 通过 load_skill_content 按需加载
    - Tier 3: 参考文件 - 通过 load_skill_ref 加载支撑文件
    """

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or SKILLS_DIR
        self._skills_meta: dict[str, SkillMeta] = {}
        self._lock = threading.Lock()

        # LRU 缓存: 完整 skill 内容缓存
        self._content_cache: OrderedDict[str, str] = OrderedDict()

        # 平台信息
        self._platform = PLATFORM_MAP.get(sys.platform, sys.platform)

        self._load_metadata()

    @staticmethod
    def _normalize_str_list(value) -> list[str]:
        """规范化字符串或列表为字符串列表 (逗号分隔自动拆分)"""
        if isinstance(value, str):
            return [t.strip() for t in value.split(",") if t.strip()]
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def _load_metadata(self):
        """加载所有 skill 元数据 (支持磁盘快照加速)"""
        snapshot = load_snapshot(self.skills_dir)
        if snapshot and snapshot.get("skills"):
            for name, meta in snapshot["skills"].items():
                # 将缓存中的 list 类型字段转换回 set
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
                    "triggers_lower": {t.lower() for t in triggers},  # 预处理：小写 set 用于快速匹配
                    "platforms": self._normalize_str_list(meta.get("platforms", [])),
                    "allowed_tools": meta.get("allowed-tools", ""),
                    "requires_tools": self._normalize_str_list(metadata.get("requires_tools", [])),
                    "fallback_for_tools": self._normalize_str_list(metadata.get("fallback_for_tools", [])),
                }
                # 预处理：description 关键词集合（避免每次匹配时重新计算）
                desc = self._skills_meta[meta["name"]]["description"]
                desc_words = set(re.findall(r"[a-zA-Z0-9_]+", desc.lower()))
                desc_words.update(re.findall(r"[\u4e00-\u9fa5]+", desc.lower()))
                self._skills_meta[meta["name"]]["desc_words"] = desc_words
            except Exception as e:
                logger.debug(f"Failed to parse skill metadata from {skill_file}: {type(e).__name__}")
                continue

        save_snapshot(self.skills_dir, self._skills_meta)

    def _normalize_triggers(self, triggers) -> list[str]:
        """规范化 triggers (字符串、列表或嵌套列表)"""
        if isinstance(triggers, str):
            return self._normalize_str_list(triggers)
        if isinstance(triggers, list):
            return self._flatten_triggers(triggers)
        return []

    def _parse_frontmatter(self, skill_file: Path) -> dict | None:
        """解析 SKILL.md 的 YAML frontmatter"""
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

    def _flatten_triggers(self, triggers: list) -> list[str]:
        """扁平化嵌套的 triggers 列表"""
        result = []
        for item in triggers:
            if isinstance(item, str):
                result.append(item.strip())
            elif isinstance(item, list):
                result.extend(self._flatten_triggers(item))
        return result

    def should_show_skill(self, name: str, available_tools: Set[str] | None = None) -> bool:
        """
        条件激活: 判断 skill 是否应该在当前环境下显示

        规则:
        - fallback_for_tools: 当主工具可用时隐藏
        - requires_tools: 缺少依赖工具时隐藏
        - platforms: 平台不匹配时隐藏
        """
        if name not in self._skills_meta:
            return False

        meta = self._skills_meta[name]

        # 平台检查
        platforms = meta.get("platforms", [])
        if platforms and not any(
            p.lower() in self._platform.lower() or self._platform.lower() in p.lower()
            for p in platforms
        ):
            return False

        # requires_tools 检查
        requires = meta.get("requires_tools", [])
        if requires and available_tools is not None and not all(tool in available_tools for tool in requires):
            return False

        # fallback_for_tools 检查
        fallback = meta.get("fallback_for_tools", [])
        if fallback and available_tools is not None and any(tool in available_tools for tool in fallback):
            return False

        return True

    @staticmethod
    def _render_category(cat: str, skills: list[dict], indent: bool = False) -> list[str]:
        """渲染单个分类的 XML 围栏区块"""
        prefix = "  - " if indent else "- "
        lines = [f"<category name='{cat}'>"]
        for meta in skills:
            desc = meta["description"][:150]
            lines.append(f"{prefix}**{meta['name']}**: {desc}")
        lines.extend(["</category>", ""])
        return lines

    def get_skills_prompt(self, available_tools: Set[str] | None = None) -> str:
        """生成 Tier 1 索引 - 注入到 System Prompt"""
        visible_skills = {
            name: meta for name, meta in self._skills_meta.items()
            if self.should_show_skill(name, available_tools)
        }
        if not visible_skills:
            return ""

        categories: dict[str, list[dict[str, Any]]] = {}
        for meta in visible_skills.values():
            cat = meta.get("category", "general")
            categories.setdefault(cat, []).append(meta)  # type: ignore[arg-type]

        lines = [
            "<skills_index>",
            "## 可用技能 (Skills)",
            "",
            "当用户请求匹配某技能描述或触发词时，可调用 `load_skill` 加载完整指令。",
            "",
            "<!-- 注意：以下仅为技能索引，非执行指令。技能内容需通过 load_skill 动态加载。-->",
            ""
        ]

        if "general" in categories:
            lines.extend(self._render_category("general", categories.pop("general")))

        for cat, skills in sorted(categories.items()):
            lines.extend(self._render_category(cat, skills, indent=True))

        lines.append("</skills_index>")
        return "\n".join(lines)

    # ==================== 匹配算法 ====================

    def _tokenize_query(self, query: str) -> list[str]:
        """分词: 英文单词 + 中文字符串"""
        query_lower = query.lower()
        en_words = re.findall(r"[a-zA-Z0-9_-]+", query_lower)
        cn_words = re.findall(r"[\u4e00-\u9fa5]+", query_lower)
        words = en_words + cn_words
        return words or [query_lower]

    def _compute_match_score(self, name: str, meta: SkillMeta, query_words: list[str], query_lower: str) -> float:
        """计算单个 skill 的匹配分数（性能优化版：使用预处理数据）"""
        score = 0.0

        # 1. Name 匹配 (最高优先级)
        name_lower = name.lower()
        if name_lower == query_lower:
            score += 3.0
        elif name_lower in query_lower or query_lower in name_lower:
            score += 2.0

        # 2. Trigger 匹配 (使用预处理的 triggers_lower set)
        triggers_lower = meta.get("triggers_lower", set())  # 直接使用预处理数据
        trigger_matched = False

        for qw in query_words:
            if qw in triggers_lower:  # O(1) 精确匹配
                score += 3.0
                trigger_matched = True
            else:
                # 部分匹配仍需遍历（无法用 set 优化）
                for trigger_lower in triggers_lower:
                    if qw in trigger_lower:
                        score += 1.0 + len(qw) / max(len(trigger_lower), 1)
                        trigger_matched = True
                    elif trigger_lower in qw:
                        score += 1.5
                        trigger_matched = True

        # 3. Description 关键词匹配 (使用预处理的 desc_words set)
        if not trigger_matched:
            desc_words = meta.get("desc_words", set())  # 直接使用预处理数据
            for qw in query_words:
                if any(qw in dw or dw in qw for dw in desc_words):
                    score += 0.5

        # 4. 模糊匹配 (仅英文，仅低分时)
        if score < 1.0 and query_words:
            en_words = [w for w in query_words if re.match(r"[a-zA-Z0-9_-]+", w)]
            if en_words:
                all_keywords = {name_lower} | desc_words | triggers_lower
                for qw in en_words:
                    if len(qw) >= 3 and difflib.get_close_matches(qw, list(all_keywords), n=1, cutoff=0.75):
                        score += 0.5

        return score

    def match_skill(self, query: str, available_tools: Set[str] | None = None) -> str | None:
        """
        根据查询匹配最相关的 skill

        评分策略:
        - name 精确匹配: +3.0
        - trigger 精确匹配: +3.0
        - description 关键词匹配: +0.5
        - 模糊匹配: +0.5
        """
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

    # ==================== 内容加载 ====================

    def load_skill_content(self, name: str) -> str | None:
        """
        Tier 2: 加载完整 skill 内容

        安全检查:
        - Prompt Injection 检测
        - 符号链接逃逸检测
        - Context Fencing: 添加围栏标签明确标识技能内容边界
        """
        # 检查缓存 (线程安全)
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

        # 安全检查：Prompt Injection 检测
        injection = scan_for_injections(content)
        if injection:
            # 高危注入模式：阻止加载，返回错误
            logger.error(f"Prompt injection detected in skill '{name}': {injection}")
            return f"[Security Error] Skill '{name}' blocked due to prompt injection pattern: {injection}. The skill content contains potentially malicious patterns that could manipulate the LLM behavior."

        symlink_check = validate_skill_structure(skill_dir)
        if symlink_check:
            return f"[Security Error] {symlink_check}"

        # Context Fencing
        fenced_content = f"<skill_content name='{name}'>\n{content}\n</skill_content>"

        # 缓存 (线程安全)
        with self._lock:
            if len(self._content_cache) >= MAX_LOADED_SKILL_CACHE:
                self._content_cache.popitem(last=False)
            self._content_cache[name] = fenced_content

        return fenced_content

    def load_skill_ref(self, name: str, ref_path: str) -> str | None:
        """
        Tier 3: 加载 skill 的参考文件

        安全: 严格限制在 skill 目录内，禁止路径穿越
        """
        if name not in self._skills_meta:
            return None

        skill_dir = Path(self._skills_meta[name]["dir"])

        # 路径穿越检测
        if ".." in ref_path:
            return "Error: Path traversal ('..') is not allowed."

        target = (skill_dir / ref_path).resolve()
        if not validate_path_within_dir(target, skill_dir):
            return "Error: Path escapes skill directory."

        if not target.exists() or not target.is_file():
            return f"Reference file not found: {ref_path}"

        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"Error reading reference: {e}"

    def get_skill_info(self, name: str) -> dict[str, Any] | None:
        """获取 skill 元数据 (不含完整内容)"""
        return self._skills_meta.get(name)  # type: ignore[return-value]

    def refresh(self):
        """强制刷新元数据 (清除缓存并重新扫描)"""
        with self._lock:
            self._content_cache.clear()
        clear_snapshot()
        self._skills_meta.clear()
        self._load_metadata()

    def get_skill_names(self) -> list[str]:
        """获取所有 skill 名称列表"""
        return list(self._skills_meta.keys())

    # ==================== Memory Graph 选择算法 ====================

    def select_best_skill(
        self,
        signals: list[str],
        available_tools: Set[str] | None = None
    ) -> str | None:
        """Memory Graph 增强的 Skill 选择算法"""
        if not MEMORY_GRAPH_CONFIG.get("enabled", True):
            query = " ".join(signals) if signals else ""
            return self.match_skill(query, available_tools)

        # 基础过滤
        candidates = [
            name for name in self._skills_meta
            if self.should_show_skill(name, available_tools)
        ]
        if not candidates:
            return None

        # 计算分数并排序
        ranked = self._rank_candidates(candidates, signals)

        # 应用禁用阈值
        return self._select_best_candidate(ranked)

    def _rank_candidates(self, candidates: list[str], signals: list[str]) -> list[tuple]:
        """计算候选分数并排序"""
        scores = {}
        for skill_name in candidates:
            scores[skill_name] = self._compute_selection_score(skill_name, signals)
        return sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)

    def _select_best_candidate(self, ranked: list[tuple]) -> str | None:
        """从排序列表中返回第一个非禁用的候选"""
        ban_threshold = MEMORY_GRAPH_CONFIG["ban_threshold"]
        min_attempts = MEMORY_GRAPH_CONFIG["min_attempts_for_ban"]

        for skill_name, info in ranked:
            stats = info.get("stats", {})
            total = stats.get("total", 0)
            # 跳过被禁用的（尝试次数足够且分数过低）
            if total >= min_attempts and info["score"] < ban_threshold:
                continue
            return skill_name
        return None

    def _compute_selection_score(self, skill_name: str, signals: list[str]) -> dict:
        """计算单个 Skill 的选择分数"""
        stats = self._get_skill_outcome_stats(skill_name)
        trigger_score = self._compute_trigger_score(skill_name, signals)

        memory_weight = MEMORY_GRAPH_CONFIG["memory_weight"]
        trigger_weight = MEMORY_GRAPH_CONFIG["trigger_weight"]
        cold_penalty = MEMORY_GRAPH_CONFIG["cold_start_penalty"]

        # 处理异常情况：stats 可能包含 error 键而非 total 键
        total = stats.get("total", 0)
        if total == 0:
            # 冷启动
            score = trigger_score * cold_penalty
            memory_score = 0.0
            mode = "cold"
        else:
            memory_score = self._compute_memory_score(stats)
            score = memory_score * memory_weight + trigger_score * trigger_weight
            mode = "warm"

        return {
            "score": score,
            "mode": mode,
            "stats": stats,
            "trigger_score": trigger_score,
            "memory_score": memory_score
        }

    def _get_skill_outcome_stats(self, skill_name: str) -> dict:
        """从 session_db 获取 Skill 统计信息"""
        try:
            from .session_db import get_skill_stats
            return get_skill_stats(skill_name)
        except ImportError:
            logger.warning("session_db not available for skill stats")
            return {
                "total": 0,
                "successes": 0,
                "failures": 0,
                "laplace_rate": 0.5,
                "last_timestamp": None,
                "recent_success_rate": 0.0
            }

    def _compute_trigger_score(self, skill_name: str, signals: list[str]) -> float:
        """计算触发器匹配分数 (最大 3.0，使用预处理数据)"""
        if not signals:
            return 0.0

        meta = self._skills_meta.get(skill_name)
        if not meta:
            return 0.0

        triggers_lower = meta.get("triggers_lower", set())
        if not triggers_lower:
            return 0.0

        # 预处理信号为小写
        signals_lower = [s.lower() for s in signals]

        score = 0.0
        for signal_lower in signals_lower:
            # 精确匹配：O(1)
            if signal_lower in triggers_lower:
                score += 1.0
            else:
                # 部分匹配：遍历
                for trigger_lower in triggers_lower:
                    if signal_lower in trigger_lower or trigger_lower in signal_lower:
                        score += 0.5

        return min(score, 3.0)

    def _compute_memory_score(self, stats: dict) -> float:
        """计算记忆分数 (Laplace平滑 + 指数衰减 + 近期加成)"""
        half_life = MEMORY_GRAPH_CONFIG["half_life_days"]
        recent_boost_factor = MEMORY_GRAPH_CONFIG["recent_boost_factor"]

        # Laplace 平滑概率
        successes = stats.get("successes", 0)
        total = stats.get("total", 1)
        p = (successes + 1) / (total + 2)

        # 指数衰减
        last_ts = stats.get("last_timestamp")
        if last_ts:
            try:
                last_time = datetime.fromisoformat(last_ts)
                age_days = (datetime.now() - last_time).days
                decay_weight = 0.5 ** (age_days / half_life)
            except (ValueError, TypeError):
                decay_weight = 1.0
        else:
            decay_weight = 1.0

        # 近期成功加成
        recent_rate = stats.get("recent_success_rate", 0.0)
        recent_boost = recent_rate * recent_boost_factor

        return p * decay_weight + recent_boost

    # ==================== Gene Slice 提取 (Tier 2a) ====================

    def get_gene_slice(self, name: str) -> str | None:
        """提取 Gene slice (Tier 2a): ~230 tokens 的核心控制信号"""
        if name not in self._skills_meta:
            return None

        skill_file = Path(self._skills_meta[name]["path"])
        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        gene_fields = self._extract_gene_fields(content)
        if not gene_fields:
            return self._extract_compact_skill(content)

        output = f"[SYSTEM: Skill '{name}' activated]\n\n## Strategy\n"
        output += "".join(f"- {item}\n" for item in gene_fields.get("strategy", []))

        if gene_fields.get("avoid"):
            output += "\n## AVOID\n"
            output += "".join(f"- {item}\n" for item in gene_fields["avoid"])

        if gene_fields.get("constraints"):
            output += "\n## Constraints\n"
            constraints = gene_fields["constraints"]
            if isinstance(constraints, dict):
                output += "".join(f"- {k}: {v}\n" for k, v in constraints.items())
            elif isinstance(constraints, list):
                output += "".join(f"- {c}\n" for c in constraints)

        if gene_fields.get("validation"):
            output += "\n## Validation\n"
            output += "".join(f"- {item}\n" for item in gene_fields["validation"])

        return output

    def _extract_gene_fields(self, content: str) -> dict | None:
        """从 YAML frontmatter 提取 Gene 控制字段"""
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1].strip())
            gene_fields = {}
            for field in ["strategy", "avoid", "constraints", "validation"]:
                if field in frontmatter:
                    gene_fields[field] = frontmatter[field]
            return gene_fields or None
        except yaml.YAMLError:
            return None

    def _extract_compact_skill(self, content: str) -> str:
        """无 Gene 字段时，提取精简版 Skill"""
        if not content.startswith("---"):
            return content[:MAX_COMPACT_CONTENT]

        parts = content.split("---", 2)
        if len(parts) < 3:
            return content[:MAX_COMPACT_CONTENT]

        try:
            frontmatter = yaml.safe_load(parts[1].strip())
            name = frontmatter.get("name", "unknown")
            desc = frontmatter.get("description", "")[:200]
            triggers = frontmatter.get("triggers", [])

            output = f"[SYSTEM: Skill '{name}' activated]\n\nDescription: {desc}\n"
            if triggers:
                output += f"Triggers: {', '.join(triggers[:5])}\n"

            # 提取第一个代码块或关键指令
            body = parts[2].strip()
            first_block = self._extract_first_instruction_block(body)
            if first_block:
                output += f"\n{first_block}"

            return output[:MAX_COMPACT_CONTENT]
        except yaml.YAMLError:
            return content[:MAX_COMPACT_CONTENT]

    def _extract_first_instruction_block(self, body: str) -> str:
        """提取第一个指令块或关键段落"""
        # 提取第一个代码块
        code_match = re.search(r"```[\w]*\n(.*?)\n```", body, re.DOTALL)
        if code_match:
            return f"```{code_match.group(1)[:200]}```"

        # 提取第一个要点列表
        list_match = re.search(r"(\n[-*]\s+.+\n){1,5}", body)
        if list_match:
            return list_match.group(0)[:300]

        return ""


# ==================== 工具函数 (供 Agent 调用) ====================

# 全局 loader 实例 (避免重复扫描)
_global_loader: SkillLoader | None = None
_loader_lock = threading.Lock()


def get_loader() -> SkillLoader:
    """获取全局单例 loader"""
    global _global_loader
    if _global_loader is None:
        with _loader_lock:
            if _global_loader is None:
                _global_loader = SkillLoader()
    return _global_loader


# 兼容性别名：旧测试中使用 _get_loader 名称
_get_loader = get_loader


def load_skill(name: str) -> str:
    """
    Load complete skill content by name (Tier 2).

    Args:
        name: Skill name (e.g., 'architecture-overview')

    Returns:
        Complete SKILL.md content or error message.
    """
    loader = get_loader()
    content = loader.load_skill_content(name)
    if content:
        return (
            f"[SYSTEM: The user has invoked the \"{name}\" skill. "
            f"Follow its instructions carefully.]\n\n{content}"
        )
    return f"Skill not found: {name}. Available: {', '.join(loader.get_skill_names())}"


def list_skills() -> str:
    """List all available skills with descriptions (Tier 1)."""
    loader = get_loader()
    skills = list(loader._skills_meta.values())

    if not skills:
        return "No skills available."

    categories: dict[str, list[dict[str, Any]]] = {}
    for s in skills:
        cat = s.get("category", "general")
        categories.setdefault(cat, []).append(s)  # type: ignore[arg-type]

    output = "Available Skills:\n"
    for cat, items in sorted(categories.items()):
        output += f"\n  [{cat}]\n"
        for s in items:  # type: ignore[assignment]
            desc = s.get("description", "")[:100]
            output += f"  - {s['name']}: {desc}\n"
            triggers = s.get("triggers", [])
            if triggers:
                output += f"    Triggers: {', '.join(triggers[:5])}\n"

    return output


def search_skill(query: str) -> str:
    """Search for a skill by query string."""
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

    return f"No skill matches: {query}. Available: {', '.join(loader.get_skill_names())}"


def register_skill_tools(registry):
    """Register skill tools to the Agent system."""
    registry.register("load_skill", load_skill)
    registry.register("list_skills", list_skills)
    registry.register("search_skill", search_skill)


# 兼容性导出：保持原有私有函数名可用
_get_loader = get_loader
