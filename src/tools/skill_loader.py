"""
渐进式 Skill 加载器 - 参考 Hermes Agent 渐进式披露架构

核心优化:
1. 两级缓存 (进程内 LRU + 磁盘快照)
2. 条件激活 (requires_tools, fallback_for, platforms)
3. Prompt Injection 安全扫描
4. 分类分组索引 (按 category/platforms 分组)
5. 三级渐进式披露: 索引(Tier1) → 内容(Tier2) → 参考文件(Tier3)
6. mtime+size manifest 缓存失效机制

Memory Graph 增强:
7. 基于历史结果的选择算法 (Laplace平滑 + 指数衰减)
8. 低价值策略禁用机制 (ban threshold)
9. 冷启动处理 + 近期成功加成
10. Gene slice 提取 (Tier 2a: strategy + avoid + constraints)

Token 节约估算:
- 全量加载: ~8700 tokens (12 skills)
- 索引模式:   ~300 tokens  (96.6% 节约)
- Gene slice: ~230 tokens  (97.4% 节约)
"""

import os
import re
import sys
import json
import yaml
import hashlib
import difflib
import threading
from collections import OrderedDict
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path
from datetime import datetime

# ==================== 常量配置 ====================

SKILLS_DIR = Path(os.path.expanduser("~")) / ".seed" / "memory" / "skills"
CACHE_DIR = Path(os.path.expanduser("~")) / ".seed" / "cache"
SNAPSHOT_PATH = CACHE_DIR / "skills_snapshot.json"

# LRU 缓存配置
MAX_CACHE_ENTRIES = 8  # 最多缓存 8 个不同的技能视图配置
MAX_LOADED_SKILL_CACHE = 5  # 最多缓存 5 个已加载的完整 skill 内容

# 平台映射
PLATFORM_MAP = {
    'win32': 'windows', 'linux': 'linux', 'darwin': 'macos',
    'windows': 'windows', 'macos': 'macos',
}

# Memory Graph 配置参数
MEMORY_GRAPH_CONFIG = {
    'half_life_days': 30,           # 置信度衰减半衰期
    'ban_threshold': 0.18,          # 禁用阈值
    'min_attempts_for_ban': 2,      # 禁用前最小尝试次数
    'memory_weight': 0.6,           # 记忆分数权重
    'trigger_weight': 0.4,          # 触发匹配权重
    'cold_start_penalty': 0.5,      # 冷启动惩罚因子
    'recent_boost_factor': 0.2,     # 近期成功加成因子
    'recent_days': 30,              # "近期"定义天数
    'enabled': True,                # 是否启用 Memory Graph 选择
}

# Prompt Injection 检测模式 (参考 Hermes skills_guard.py)
INJECTION_PATTERNS = [
    "ignore previous instructions", "ignore all previous",
    "you are now", "disregard your", "forget your instructions",
    "new instructions:", "system prompt:", "<system>", "]]>",
    "ignore all the instructions", "you must forget",
]

# ==================== 磁盘快照缓存 (Layer 2) ====================

def _build_manifest(skills_dir: Path) -> str:
    """构建技能目录的 manifest (mtime + size) 用于缓存失效检测"""
    if not skills_dir.exists():
        return ""
    manifest = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                stat = skill_file.stat()
                manifest[str(skill_dir.name)] = {
                    'mtime': stat.st_mtime,
                    'size': stat.st_size,
                }
    return hashlib.md5(json.dumps(manifest, sort_keys=True).encode()).hexdigest()

def load_snapshot(skills_dir: Path) -> Optional[Dict]:
    """从磁盘加载缓存快照"""
    try:
        if not SNAPSHOT_PATH.exists():
            return None
        with open(SNAPSHOT_PATH, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
        # 检查 manifest 是否匹配
        current_manifest = _build_manifest(skills_dir)
        if snapshot.get('manifest') != current_manifest:
            return None  # 文件已变更，快照失效
        return snapshot
    except (json.JSONDecodeError, OSError):
        return None

def save_snapshot(skills_dir: Path, skills_meta: Dict) -> None:
    """保存缓存快照到磁盘"""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        snapshot = {
            'manifest': _build_manifest(skills_dir),
            'timestamp': datetime.now().isoformat(),
            'skills': skills_meta,
        }
        # 原子写入
        tmp_path = SNAPSHOT_PATH.with_suffix('.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SNAPSHOT_PATH)
    except OSError:
        pass

def clear_snapshot() -> None:
    """清除磁盘快照 (在 skill 被 patch 后调用)"""
    try:
        if SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.unlink()
    except OSError:
        pass


# ==================== 安全扫描 ====================

def _scan_for_injections(content: str) -> Optional[str]:
    """检测 Skill 内容中的 Prompt Injection 攻击"""
    content_lower = content.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in content_lower:
            return f"Potential prompt injection detected: '{pattern}'"
    return None

def _validate_skill_structure(skill_dir: Path) -> Optional[str]:
    """验证 Skill 目录结构安全"""
    try:
        # 检查符号链接逃逸
        for item in skill_dir.rglob('*'):
            if item.is_symlink():
                resolved = item.resolve()
                if not str(resolved).startswith(str(skill_dir.resolve())):
                    return f"Symlink escape detected: {item} -> {resolved}"
        # 检查二进制文件
        suspicious_ext = {'.exe', '.dll', '.so', '.dylib', '.bin', '.dat', '.com'}
        for item in skill_dir.rglob('*'):
            if item.is_file() and item.suffix.lower() in suspicious_ext:
                return f"Suspicious binary file: {item}"
    except (OSError, PermissionError):
        pass
    return None


# ==================== SkillLoader 核心类 ====================

class SkillLoader:
    """
    渐进式 Skill 加载器
    
    三级披露:
    - Tier 1: 索引 (name + description + triggers) - 注入 System Prompt
    - Tier 2: 完整内容 - 通过 load_skill 按需加载
    - Tier 3: 参考文件 - 通过 load_skill_ref 加载支撑文件
    """

    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir or SKILLS_DIR
        self._skills_meta: Dict[str, Dict] = {}
        self._manifest_hash: str = ""
        self._lock = threading.Lock()
        
        # LRU 缓存: 完整 skill 内容缓存
        self._content_cache: OrderedDict[str, str] = OrderedDict()
        
        # 平台信息
        self._platform = PLATFORM_MAP.get(sys.platform, sys.platform)
        
        self._load_metadata()

    def _load_metadata(self):
        """加载所有 skill 元数据 (支持磁盘快照加速)"""
        # 尝试从磁盘快照加载
        snapshot = load_snapshot(self.skills_dir)
        if snapshot and snapshot.get('skills'):
            for name, meta in snapshot['skills'].items():
                self._skills_meta[name] = meta
            self._manifest_hash = snapshot.get('manifest', '')
            return
        
        # 快照失效或不存在，执行全量扫描
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
                if meta and 'name' in meta:
                    # 解析 triggers
                    triggers = meta.get('triggers', [])
                    if isinstance(triggers, str):
                        triggers = [t.strip() for t in triggers.split(',') if t.strip()]
                    elif not isinstance(triggers, list):
                        triggers = []

                    # 解析 platforms
                    platforms = meta.get('platforms', [])
                    if isinstance(platforms, str):
                        platforms = [p.strip() for p in platforms.split(',')]

                    # 解析条件激活字段
                    metadata = meta.get('metadata', {}) or {}
                    requires_tools = metadata.get('requires_tools', [])
                    if isinstance(requires_tools, str):
                        requires_tools = [t.strip() for t in requires_tools.split(',') if t.strip()]
                    
                    fallback_for_tools = metadata.get('fallback_for_tools', [])
                    if isinstance(fallback_for_tools, str):
                        fallback_for_tools = [t.strip() for t in fallback_for_tools.split(',') if t.strip()]

                    self._skills_meta[meta['name']] = {
                        'path': str(skill_file),
                        'dir': str(skill_dir),
                        'name': meta['name'],
                        'description': meta.get('description', '')[:300],
                        'category': meta.get('category', 'general'),
                        'version': meta.get('version', '1.0'),
                        'triggers': triggers,
                        'platforms': platforms,
                        'allowed_tools': meta.get('allowed-tools', ''),
                        'requires_tools': requires_tools,
                        'fallback_for_tools': fallback_for_tools,
                    }
            except Exception:
                continue

        # 保存快照
        save_snapshot(self.skills_dir, self._skills_meta)
        self._manifest_hash = _build_manifest(self.skills_dir)

    def _parse_frontmatter(self, skill_file: Path) -> Optional[Dict]:
        """解析 SKILL.md 的 YAML frontmatter"""
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            return yaml.safe_load(parts[1].strip())
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            return None

    def should_show_skill(self, name: str, available_tools: Set[str] = None) -> bool:
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
        platforms = meta.get('platforms', [])
        if platforms:
            platform_matched = any(
                p.lower() in self._platform.lower() or 
                self._platform.lower() in p.lower() 
                for p in platforms
            )
            if not platform_matched:
                return False
        
        # requires_tools 检查
        requires = meta.get('requires_tools', [])
        if requires and available_tools is not None:
            for tool in requires:
                if tool not in available_tools:
                    return False  # 缺少必需工具
        
        # fallback_for_tools 检查
        fallback = meta.get('fallback_for_tools', [])
        if fallback and available_tools is not None:
            for tool in fallback:
                if tool in available_tools:
                    return False  # 主工具已存在，不需要 fallback
        
        return True

    def get_skills_prompt(self, available_tools: Set[str] = None) -> str:
        """
        生成 Tier 1 索引 - 注入到 System Prompt
        
        优化:
        - 按 category 分组
        - 仅显示应激活的 skill
        - 每个 skill 仅一行 (name + 短描述)
        """
        # 过滤出应显示的 skill
        visible_skills = {}
        for name, meta in self._skills_meta.items():
            if self.should_show_skill(name, available_tools):
                visible_skills[name] = meta
        
        if not visible_skills:
            return ""
        
        # 按 category 分组
        categories: Dict[str, List[Dict]] = {}
        for meta in visible_skills.values():
            cat = meta.get('category', 'general')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(meta)
        
        lines = ["## 可用技能 (Skills)", ""]
        lines.append("当用户请求匹配某技能描述或触发词时，可调用 `load_skill` 加载完整指令。")
        lines.append("")
        
        # 通用技能 (无分类或 general)
        if 'general' in categories:
            for meta in categories['general']:
                desc = meta['description'][:150]
                lines.append(f"- **{meta['name']}**: {desc}")
            lines.append("")
            del categories['general']
        
        # 其他分类
        for cat, skills in sorted(categories.items()):
            lines.append(f"**{cat}**:")
            for meta in skills:
                desc = meta['description'][:150]
                lines.append(f"  - **{meta['name']}**: {desc}")
            lines.append("")
        
        return "\n".join(lines)

    def _tokenize_query(self, query: str) -> Tuple[List[str], List[str], List[str]]:
        """分词: 英文单词 + 中文字符串"""
        query_lower = query.lower()
        en_words = re.findall(r'[a-zA-Z0-9_-]+', query_lower)
        cn_words = re.findall(r'[\u4e00-\u9fa5]+', query_lower)
        query_words = en_words + cn_words
        if not query_words and query.strip():
            query_words = [query_lower]
        return en_words, cn_words, query_words

    def _score_name_match(self, name: str, query_lower: str) -> float:
        """Name 精确匹配: +3.0"""
        if name.lower() == query_lower or name.lower() in query_lower or query_lower in name.lower():
            return 3.0
        return 0.0

    def _score_trigger_match(self, triggers: List[str], query_words: List[str]) -> Tuple[float, bool]:
        """
        Trigger 匹配 - 精确匹配优先于部分匹配
        返回 (score, matched)
        """
        for trigger in triggers:
            trigger_lower = trigger.lower()
            for qw in query_words:
                if trigger_lower == qw:
                    # 精确匹配 - 最高优先级
                    return 3.0, True
                elif qw in trigger_lower:
                    # 查询词是触发词的子串 (e.g. "诊断" in "诊断趋势")
                    ratio = len(qw) / max(len(trigger_lower), 1)
                    return 1.0 + ratio, True  # 1.0~2.0
                elif trigger_lower in qw:
                    # 触发词是查询词的子串
                    return 1.5, True
        return 0.0, False

    def _score_description_match(self, description: str, query_words: List[str]) -> Tuple[float, Set[str]]:
        """
        Description 关键词匹配 (仅在没有 trigger 匹配时生效)
        返回 (score, desc_words)
        """
        desc_words = set(re.findall(r'[a-zA-Z0-9_]+', description.lower()))
        desc_words.update(re.findall(r'[\u4e00-\u9fa5]+', description.lower()))
        score = 0.0
        for qw in query_words:
            for dw in desc_words:
                if qw in dw or dw in qw:
                    score += 0.5
                    break
        return score, desc_words

    def _score_fuzzy_match(self, name: str, triggers: List[str], desc_words: Set[str],
                           en_words: List[str], current_score: float) -> float:
        """模糊匹配 (仅英文，仅在当前得分 < 1.0 时生效)"""
        if current_score >= 1.0 or not en_words:
            return 0.0
        all_keywords = set()
        all_keywords.add(name.lower())
        all_keywords.update(desc_words)
        all_keywords.update(t.lower() for t in triggers)
        keyword_list = list(all_keywords)
        score = 0.0
        for qw in en_words:
            if len(qw) >= 3:
                matches = difflib.get_close_matches(qw, keyword_list, n=1, cutoff=0.75)
                if matches:
                    score += 0.5
        return score

    def match_skill(self, query: str, available_tools: Set[str] = None) -> Optional[str]:
        """
        根据查询匹配最相关的 skill

        评分策略:
        - name 精确匹配: +3.0
        - trigger 精确匹配: +2.0
        - description 关键词匹配: +1.0
        - 模糊匹配: +0.5
        """
        query_lower = query.lower()
        en_words, cn_words, query_words = self._tokenize_query(query)

        best_match = None
        best_score = 0.0

        for name, meta in self._skills_meta.items():
            # 条件激活过滤
            if not self.should_show_skill(name, available_tools):
                continue

            score = 0.0

            # 1. Name 精确匹配
            score += self._score_name_match(name, query_lower)

            # 2. Trigger 匹配
            triggers = meta.get('triggers', [])
            trigger_score, trigger_matched = self._score_trigger_match(triggers, query_words)
            score += trigger_score

            # 3. Description 关键词匹配 (仅在没有 trigger 匹配时生效)
            if not trigger_matched:
                desc_score, desc_words = self._score_description_match(meta['description'], query_words)
                score += desc_score
            else:
                desc_words = set()

            # 4. 模糊匹配 (仅英文)
            score += self._score_fuzzy_match(name, triggers, desc_words, en_words, score)

            if score > best_score:
                best_score = score
                best_match = name

        return best_match if best_score >= 1.0 else None

    def load_skill_content(self, name: str) -> Optional[str]:
        """
        Tier 2: 加载完整 skill 内容
        
        安全检查:
        - Prompt Injection 检测
        - 路径穿越检测 (通过 validate_within_dir)
        - 符号链接逃逸检测
        """
        # 检查缓存
        if name in self._content_cache:
            self._content_cache.move_to_end(name)
            return self._content_cache[name]
        
        if name not in self._skills_meta:
            return None
        
        skill_dir = Path(self._skills_meta[name]['dir'])
        skill_file = Path(self._skills_meta[name]['path'])
        
        if not skill_file.exists():
            return None
        
        try:
            content = skill_file.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return None
        
        # 安全检查
        injection = _scan_for_injections(content)
        if injection:
            return f"[Security Warning] {injection}\n\n{content}"
        
        symlink_check = _validate_skill_structure(skill_dir)
        if symlink_check:
            return f"[Security Warning] {symlink_check}"
        
        # 缓存
        if len(self._content_cache) >= MAX_LOADED_SKILL_CACHE:
            self._content_cache.popitem(last=False)
        self._content_cache[name] = content
        
        return content

    def load_skill_ref(self, name: str, ref_path: str) -> Optional[str]:
        """
        Tier 3: 加载 skill 的参考文件
        
        安全: 严格限制在 skill 目录内，禁止路径穿越
        """
        if name not in self._skills_meta:
            return None
        
        skill_dir = Path(self._skills_meta[name]['dir'])
        
        # 路径穿越检测
        if '..' in ref_path:
            return "Error: Path traversal ('..') is not allowed."
        
        target = (skill_dir / ref_path).resolve()
        if not str(target).startswith(str(skill_dir.resolve())):
            return "Error: Path escapes skill directory."
        
        if not target.exists() or not target.is_file():
            return f"Reference file not found: {ref_path}"
        
        try:
            return target.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            return f"Error reading reference: {e}"

    def get_skill_info(self, name: str) -> Optional[Dict]:
        """获取 skill 元数据 (不含完整内容)"""
        return self._skills_meta.get(name)

    def refresh(self):
        """强制刷新元数据 (清除缓存并重新扫描)"""
        self._content_cache.clear()
        clear_snapshot()
        self._skills_meta.clear()
        self._load_metadata()

    def get_skill_names(self) -> List[str]:
        """获取所有 skill 名称列表"""
        return list(self._skills_meta.keys())

    # ==================== Memory Graph 选择算法 ====================

    def select_best_skill(
        self,
        signals: List[str],
        available_tools: Set[str] = None
    ) -> Optional[str]:
        """
        Memory Graph 增强的 Skill 选择算法

        流程:
        1. 过滤候选 (平台 + 工具可用性)
        2. 计算选择分数:
           - 查询 gene_outcomes 获取成功率
           - 应用 Laplace 平滑 + 指数衰减
           - 添加近期成功加成
           - 结合触发器匹配分数
        3. 检查禁用阈值
        4. 返回最高分数候选（跳过被禁用的）

        Args:
            signals: 触发信号列表（从上下文提取）
            available_tools: 可用工具集合

        Returns:
            最佳 Skill 名称，或 None（无候选）
        """
        if not MEMORY_GRAPH_CONFIG.get('enabled', True):
            # 未启用 Memory Graph，使用传统匹配
            query = ' '.join(signals) if signals else ''
            return self.match_skill(query, available_tools)

        # Step 1: 基础过滤
        candidates = [
            name for name in self._skills_meta
            if self.should_show_skill(name, available_tools)
        ]

        if not candidates:
            return None

        # Step 2: 分数计算
        skill_scores: Dict[str, Dict] = {}

        for skill_name in candidates:
            score_info = self._compute_skill_selection_score(
                skill_name, signals
            )
            skill_scores[skill_name] = score_info

        # Step 3: 排序并应用禁用阈值
        ranked = sorted(
            skill_scores.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )

        ban_threshold = MEMORY_GRAPH_CONFIG['ban_threshold']
        min_attempts = MEMORY_GRAPH_CONFIG['min_attempts_for_ban']

        for skill_name, info in ranked:
            stats = info.get('stats', {})

            # 禁用检查: 2+ 次尝试 + 分数低于阈值
            if stats.get('total', 0) >= min_attempts:
                if info['score'] < ban_threshold:
                    continue  # 跳过被禁用的，尝试下一个

            return skill_name

        # 所有候选都被禁用
        return None

    def _compute_skill_selection_score(
        self,
        skill_name: str,
        signals: List[str]
    ) -> Dict:
        """
        计算单个 Skill 的选择分数

        Returns:
            {
                'score': float,
                'mode': 'cold' | 'warm',
                'stats': {...},
                'trigger_score': float,
                'memory_score': float
            }
        """
        # 获取历史统计
        stats = self._get_skill_outcome_stats(skill_name)

        # 计算触发器匹配分数
        trigger_score = self._compute_trigger_match_score(skill_name, signals)

        memory_weight = MEMORY_GRAPH_CONFIG['memory_weight']
        trigger_weight = MEMORY_GRAPH_CONFIG['trigger_weight']
        cold_penalty = MEMORY_GRAPH_CONFIG['cold_start_penalty']

        if stats['total'] == 0:
            # 冷启动：无历史
            score = trigger_score * cold_penalty
            mode = 'cold'
            memory_score = 0.0
        else:
            # 有历史：计算记忆分数
            memory_score = self._compute_memory_score(stats)
            score = memory_score * memory_weight + trigger_score * trigger_weight
            mode = 'warm'

        return {
            'score': score,
            'mode': mode,
            'stats': stats,
            'trigger_score': trigger_score,
            'memory_score': memory_score
        }

    def _get_skill_outcome_stats(self, skill_name: str) -> Dict:
        """
        从 gene_outcomes 获取 Skill 统计信息

        Returns:
            {
                'total': N,
                'successes': N,
                'failures': N,
                'laplace_rate': 0.XX,
                'last_timestamp': ISO,
                'recent_success_rate': 0.XX
            }
        """
        try:
            from src.tools.session_db import get_skill_stats
            stats = get_skill_stats(skill_name)
            return stats
        except ImportError:
            # 模块不可用，返回空统计
            return {
                'total': 0,
                'successes': 0,
                'failures': 0,
                'laplace_rate': 0.5,
                'last_timestamp': None,
                'recent_success_rate': 0.0
            }

    def _compute_trigger_match_score(
        self,
        skill_name: str,
        signals: List[str]
    ) -> float:
        """
        计算触发器匹配分数

        评分规则:
        - 每个精确匹配: 1.0
        - 每个部分匹配: 0.5
        - 最大分数上限: 3.0
        """
        if not signals:
            return 0.0

        meta = self._skills_meta.get(skill_name)
        if not meta:
            return 0.0

        triggers = meta.get('triggers', [])
        if not triggers:
            return 0.0

        score = 0.0
        max_score = 3.0

        for signal in signals:
            signal_lower = signal.lower()
            for trigger in triggers:
                trigger_lower = trigger.lower()

                if trigger_lower == signal_lower:
                    score += 1.0  # 精确匹配
                elif signal_lower in trigger_lower or trigger_lower in signal_lower:
                    score += 0.5  # 部分匹配

        return min(score, max_score)

    def _compute_memory_score(self, stats: Dict) -> float:
        """
        计算记忆分数 (GEP-style)

        公式: value = laplace_rate * decay_weight + recent_boost

        Args:
            stats: 从 gene_outcomes 获取的统计信息

        Returns:
            记忆分数 (0.0 - 1.0)
        """
        half_life = MEMORY_GRAPH_CONFIG['half_life_days']
        recent_boost_factor = MEMORY_GRAPH_CONFIG['recent_boost_factor']

        # Laplace 平滑概率
        successes = stats.get('successes', 0)
        total = stats.get('total', 1)
        p = (successes + 1) / (total + 2)

        # 指数衰减（基于最近执行时间）
        last_ts = stats.get('last_timestamp')
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
        recent_rate = stats.get('recent_success_rate', 0.0)
        recent_boost = recent_rate * recent_boost_factor

        return p * decay_weight + recent_boost

    # ==================== Gene Slice 提取 (Tier 2a) ====================

    def get_gene_slice(self, name: str) -> Optional[str]:
        """
        提取 Gene slice (Tier 2a): ~230 tokens 的核心控制信号

        包含:
        - strategy: 有序操作步骤
        - avoid: 失败警告
        - constraints: 安全边界
        - validation: 后执行验证

        Returns:
            格式化的 Gene slice 字符串，或 None
        """
        if name not in self._skills_meta:
            return None

        content = self.load_skill_content(name)
        if not content:
            return None

        # 解析 frontmatter 提取控制字段
        gene_fields = self._extract_gene_fields(content)

        if not gene_fields:
            # 无 Gene 字段，返回精简版 skill（仅 frontmatter）
            return self._extract_compact_skill(content)

        # 格式化 Gene slice
        output = f"[SYSTEM: Skill '{name}' activated]\n\n"
        output += "## Strategy\n"
        for step in gene_fields.get('strategy', []):
            output += f"- {step}\n"

        if gene_fields.get('avoid'):
            output += "\n## AVOID\n"
            for warning in gene_fields['avoid']:
                output += f"- {warning}\n"

        if gene_fields.get('constraints'):
            output += "\n## Constraints\n"
            constraints = gene_fields['constraints']
            if isinstance(constraints, dict):
                for k, v in constraints.items():
                    output += f"- {k}: {v}\n"
            elif isinstance(constraints, list):
                for c in constraints:
                    output += f"- {c}\n"

        if gene_fields.get('validation'):
            output += "\n## Validation\n"
            for check in gene_fields['validation']:
                output += f"- {check}\n"

        return output

    def _extract_gene_fields(self, content: str) -> Optional[Dict]:
        """
        从 SKILL.md 内容提取 Gene 控制字段

        Gene 字段位于 YAML frontmatter 中:
        - strategy: List[str]
        - avoid: List[str]
        - constraints: Dict | List[str]
        - validation: List[str]
        """
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1].strip())

            gene_fields = {}
            for field in ['strategy', 'avoid', 'constraints', 'validation']:
                if field in frontmatter:
                    gene_fields[field] = frontmatter[field]

            return gene_fields if gene_fields else None
        except yaml.YAMLError:
            return None

    def _extract_compact_skill(self, content: str) -> str:
        """
        无 Gene 字段时，提取精简版 Skill

        仅包含: name, description, triggers
        """
        if not content.startswith("---"):
            return content[:500]  # 无 frontmatter，截取前 500 字符

        parts = content.split("---", 2)
        if len(parts) < 3:
            return content[:500]

        try:
            frontmatter = yaml.safe_load(parts[1].strip())
            name = frontmatter.get('name', 'unknown')
            desc = frontmatter.get('description', '')[:200]
            triggers = frontmatter.get('triggers', [])

            output = f"[SYSTEM: Skill '{name}' activated]\n\n"
            output += f"Description: {desc}\n"
            if triggers:
                output += f"Triggers: {', '.join(triggers[:5])}\n"

            # 提取第一个代码块或关键指令
            body = parts[2].strip()
            first_block = self._extract_first_instruction_block(body)
            if first_block:
                output += f"\n{first_block}"

            return output[:500]  # Token 限制
        except yaml.YAMLError:
            return content[:500]

    def _extract_first_instruction_block(self, body: str) -> str:
        """提取第一个指令块或关键段落"""
        # 提取第一个代码块
        code_match = re.search(r'```[\w]*\n(.*?)\n```', body, re.DOTALL)
        if code_match:
            return f"```{code_match.group(1)[:200]}```"

        # 提取第一个要点列表
        list_match = re.search(r'(\n[-*]\s+.+\n){1,5}', body)
        if list_match:
            return list_match.group(0)[:300]

        return ""


# ==================== 工具函数 (供 Agent 调用) ====================

# 全局 loader 实例 (避免重复扫描)
_global_loader: Optional[SkillLoader] = None
_loader_lock = threading.Lock()

def _get_loader() -> SkillLoader:
    """获取全局单例 loader"""
    global _global_loader
    if _global_loader is None:
        with _loader_lock:
            if _global_loader is None:
                _global_loader = SkillLoader()
    return _global_loader


def load_skill(name: str) -> str:
    """
    Load complete skill content by name (Tier 2).

    Args:
        name: Skill name (e.g., 'architecture-overview')

    Returns:
        Complete SKILL.md content or error message.
    """
    loader = _get_loader()
    content = loader.load_skill_content(name)
    if content:
        # 以 SYSTEM 标记注入，提升指令跟随权重 (参考 Hermes)
        return (
            f"[SYSTEM: The user has invoked the \"{name}\" skill. "
            f"Follow its instructions carefully.]\n\n"
            f"{content}"
        )
    return f"Skill not found: {name}. Available: {', '.join(loader.get_skill_names())}"


def list_skills() -> str:
    """
    List all available skills with descriptions (Tier 1).

    Returns:
        Formatted list of skills grouped by category.
    """
    loader = _get_loader()
    skills = list(loader._skills_meta.values())

    if not skills:
        return "No skills available."

    # 按 category 分组
    categories: Dict[str, List[Dict]] = {}
    for s in skills:
        cat = s.get('category', 'general')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(s)

    output = "Available Skills:\n"
    for cat, items in sorted(categories.items()):
        output += f"\n  [{cat}]\n"
        for s in items:
            desc = s.get('description', '')[:100]
            output += f"  - {s['name']}: {desc}\n"
            triggers = s.get('triggers', [])
            if triggers:
                output += f"    Triggers: {', '.join(triggers[:5])}\n"

    return output


def search_skill(query: str) -> str:
    """
    Search for a skill by query string.

    Args:
        query: Search query

    Returns:
        Matched skill content or list of candidates.
    """
    loader = _get_loader()
    match = loader.match_skill(query)
    
    if match:
        content = loader.load_skill_content(match)
        if content:
            return f"[Matched] {match}\n\n{content}"
    
    # 返回候选列表
    candidates = []
    query_lower = query.lower()
    for name, meta in loader._skills_meta.items():
        if query_lower in name.lower() or query_lower in meta['description'].lower():
            candidates.append(f"- {name}: {meta['description'][:100]}")
    
    if candidates:
        return f"No exact match. Candidates:\n" + "\n".join(candidates)
    
    return f"No skill matches: {query}. Available: {', '.join(loader.get_skill_names())}"


def register_skill_tools(registry):
    """Register skill tools to the Agent system."""
    registry.register("load_skill", load_skill)
    registry.register("list_skills", list_skills)
    registry.register("search_skill", search_skill)
