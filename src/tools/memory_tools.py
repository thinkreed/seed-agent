"""
记忆工具模块

负责:
1. 四级记忆写入 (L1 索引、L2 技能、L3 知识、L4 原始数据)
2. 会话历史管理 (SQLite 存储、JSONL 备份)
3. 技能执行结果记录 (gene_outcomes 表、成功率追踪)
4. 记忆内容验证 (长度限制、格式检查、YAML frontmatter)
5. 会话文件管理 (按时间分割、归档清理)

核心功能:
- write_memory: 标准化记忆写入接口
- _save_session_history: 会话持久化
- _record_skill_outcome: 技能执行追踪
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from . import ToolRegistry

logger = logging.getLogger(__name__)

# 定位 ~/.seed/memory
MEMORY_ROOT = os.path.join(os.path.expanduser("~"), ".seed", "memory")
SESSIONS_DIR = os.path.join(MEMORY_ROOT, "raw", "sessions")


def write_memory(level: str, content: str, title: str = "", metadata: str = "") -> str:
    """
    Write memory to L1/L2/L3/L4. Validates content length and structure.

    Args:
        level: L1 (Index), L2 (Skill), L3 (Knowledge), L4 (Raw)
        content: Memory content (for L2, must be SKILL.md format with YAML frontmatter)
        title: Memory title or skill name (for L2-L4). For L1, it's the section header.
        metadata: Optional metadata (source, date, etc.)
    """
    # L1 校验：索引简短，无详细步骤
    if level == "L1":
        if len(content) > 200:
            return "Error: L1 content exceeds 200 chars (Index only)."
        if "##" in content or "```" in content:
            return "Error: L1 cannot contain subsections or code blocks."

    # L2 校验：必须符合 Open Agent Skills 规范
    if level == "L2":
        validation = _validate_skill_format(content, title)
        if validation:
            return validation

    path = _get_path(level, title)
    if not path:
        return "Error: Invalid level or missing filename."

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if level == "L1":
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n## {title}\n")
                f.write(content.strip() + "\n")
            return f"Updated L1 Index: {title}"
        # L2 直接写入 content（已包含 YAML frontmatter）
        # L3/L4 写入带标题的格式
        if level == "L2":
            # L2 写入 SKILL.md 格式（content 应已包含 frontmatter）
            with open(path, "w", encoding="utf-8") as f:
                f.write(content.strip() + "\n")
        else:
            with open(path, "w", encoding="utf-8") as f:
                if metadata:
                    f.write(f"<!-- {metadata} -->\n")
                f.write(f"# {title}\n")
                f.write(content.strip() + "\n")
        return f"Saved {level} Memory: {os.path.basename(path)}"
    except PermissionError:
        return f"Error writing memory: Permission denied - {path}"
    except OSError as e:
        return f"Error writing memory: OS error - {type(e).__name__}: {str(e)[:100]}"
    except Exception as e:
        # 完整错误记录到日志
        logger.exception(
            f"Unexpected error writing memory to {path}: {type(e).__name__}: {e}"
        )
        return f"Error writing memory: {type(e).__name__}: {str(e)[:100]}"


def _validate_skill_format(content: str, name: str = "") -> str:
    """校验 L2 Skill 格式是否符合 Open Agent Skills 规范"""
    # 校验 YAML frontmatter
    if not content.strip().startswith("---"):
        return "Error: L2 Skill must start with YAML frontmatter (---)."

    # 提取 frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return "Error: L2 Skill must have closing --- for frontmatter."

    frontmatter_text = parts[1].strip()

    # 校验必需字段
    required_fields = ["name", "description"]
    for field in required_fields:
        if field not in frontmatter_text:
            return f"Error: L2 Skill frontmatter must contain '{field}' field."

    # 解析 name 字段
    name_match = re.search(r'name:\s*["\']?([^"\':\n]+)["\']?', frontmatter_text)
    if name_match:
        skill_name = name_match.group(1).strip()
        # name 校验规则：小写字母/数字/连字符，1-64字符
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", skill_name):
            return (
                f"Error: L2 Skill name '{skill_name}' must be lowercase "
                f"letters/numbers/hyphens, 1-64 chars, "
                f"no leading/trailing/consecutive hyphens."
            )
        if len(skill_name) > 64:
            return "Error: L2 Skill name exceeds 64 chars limit."

    # 校验 description 长度
    desc_match = re.search(
        r'description:\s*["\']?(.+?)["\']?\n', frontmatter_text, re.DOTALL
    )
    if desc_match:
        desc = desc_match.group(1).strip()
        if len(desc) > 1024:
            return "Error: L2 Skill description exceeds 1024 chars limit."
        if not desc:
            return "Error: L2 Skill description cannot be empty."

    # 校验文件名：必须是 skill_name/SKILL.md 格式
    if name:
        # name 应为 skill_name/SKILL.md 或 SKILL.md
        expected_name = f"{skill_name}/SKILL.md"
        if name != expected_name and name != "SKILL.md":
            return f"Error: L2 filename must be '{expected_name}' (skill directory with SKILL.md)."

    return ""  # 校验通过


def _get_path(level: str, filename: str | None = None) -> str | None:
    """获取记忆文件路径"""
    mapping = {"L1": "notes.md", "L2": "skills", "L3": "knowledge", "L4": "raw"}
    if level not in mapping:
        return None
    base = mapping[level]

    # L1 是单个文件，无需 filename
    if level == "L1":
        return os.path.join(MEMORY_ROOT, base)

    # L2-L4 需要指定 filename
    if not filename:
        return None

    # L2 特殊处理：skill 目录结构，自动补全 SKILL.md
    if level == "L2" and not filename.endswith("/SKILL.md") and filename != "SKILL.md":
        filename = os.path.join(filename, "SKILL.md")

    return os.path.join(MEMORY_ROOT, base, filename)


def read_memory_index() -> str:
    """
    Read the global memory index (L1) to find available SOPs or knowledge.

    Returns:
        Content of notes.md
    """
    path = _get_path("L1")
    if path is None or not os.path.exists(path):
        return "Memory index not found."
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading index: {e!s}"


def search_memory(keyword: str, levels: list[str] | None = None) -> str:
    """
    Search memory by keyword across L1/L2/L3.

    Args:
        keyword: Search keyword
        levels: Levels to search (default L1, L2, L3)

    Returns:
        List of matching files with levels.
    """
    if levels is None:
        levels = ["L1", "L2", "L3"]
    results = []
    if not os.path.exists(MEMORY_ROOT):
        return "Memory root not found."

    for root, _, files in os.walk(MEMORY_ROOT):
        if ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith((".md", ".txt")):
                # Determine level
                rel = os.path.relpath(root, MEMORY_ROOT)
                lvl = "Unknown"
                if "notes" in rel or file == "notes.md":
                    lvl = "L1"
                elif "skills" in rel:
                    lvl = "L2"
                elif "knowledge" in rel:
                    lvl = "L3"
                elif "raw" in rel:
                    lvl = "L4"

                if lvl in levels:
                    try:
                        fpath = os.path.join(root, file)
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            if keyword.lower() in f.read().lower():
                                results.append(f"[{lvl}] {file}")
                    except Exception as e:
                        logger.debug(
                            f"Failed to read memory file {file}: {type(e).__name__}"
                        )
                        continue
    return "\n".join(results) if results else "No matching memory found."


def start_long_term_update(args: dict[str, Any], **kwargs: Any) -> str:
    """
    Triggered when the agent believes a task is complete.
    Dynamically reads memory SOP and injects it into the prompt.
    """
    memory_md_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "memory", "memory.md"
    )
    sop_content = "[Error: Unable to load memory.md]"
    try:
        with open(memory_md_path, encoding="utf-8") as f:
            sop_content = f.read()
    except Exception as e:
        sop_content = f"Error reading SOP: {e!s}"

    return f"""### [经验提炼] 任务即将结束，请提炼并保存本次任务中的有效经验。

以下是必须严格遵守的记忆管理 SOP，请根据 SOP 中的层级定义和约束进行经验提炼：

{sop_content}

请总结以下内容并使用 `write_memory` 保存：
1. **环境事实/配置**: 经过验证的路径 (相对)、依赖、配置 (Level: L2)。
2. **SOP/技能**: 成功的操作步骤、代码片段、重试策略 (Level: L2)。
3. **避坑/知识**: 失败原因、解决方案、通用规则 (Level: L3)。
4. **用户偏好**: 特定的需求或习惯 (Level: L2)。"""


def register_memory_tools(registry: ToolRegistry) -> None:
    """Register memory tools to the Agent system."""
    registry.register("write_memory", write_memory)
    registry.register("read_memory_index", read_memory_index)
    registry.register("search_memory", search_memory)
    registry.register("start_long_term_update", start_long_term_update)
    # 对话历史工具 - 使用 SQLite + FTS5 后端
    registry.register("save_session_history", _save_session_history)
    registry.register("load_session_history", _load_session_history)
    registry.register("list_sessions", _list_sessions)
    registry.register("search_history", _search_history)
    # Memory Graph 工具 - Skill 执行结果追踪
    registry.register("record_skill_outcome", _record_skill_outcome)
    registry.register("get_skill_stats", _get_skill_stats)
    registry.register("list_banned_skills", _list_banned_skills)
    registry.register("get_top_skills", _get_top_skills)
    # L4 用户建模工具 - 黑格尔辩证式进化
    registry.register("observe_user_preference", _observe_user_preference)
    registry.register("get_user_preference", _get_user_preference)
    registry.register("get_user_profile_summary", _get_user_profile_summary)
    registry.register("update_user_model", _update_user_model)
    registry.register("list_user_preferences", _list_user_preferences)
    # L5 工作日志工具 - 长期归档 + LLM摘要
    registry.register("archive_session_events", _archive_session_events)
    registry.register("search_archives", _search_archives)
    registry.register("get_archive_details", _get_archive_details)
    registry.register("get_archive_stats", _get_archive_stats)
    registry.register("get_memory_hierarchy", _get_memory_hierarchy)


# ==================== 对话历史持久化 (L4 Raw - SQLite + FTS5) ====================
# SQLite 后端实现已迁移到 session_db.py，此处为兼容性封装层。
# 迁移完成后，JSONL 文件将不再使用，但保留 _ensure_sessions_dir 等函数
# 以支持可能仍依赖它们的旧代码。


def _ensure_sessions_dir() -> None:
    """确保 sessions 目录存在（保留兼容）"""
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def _save_session_history(
    messages: list, summary: str | None = None, session_id: str | None = None
) -> str:
    """Save conversation history to SQLite (wrapper for session_db.py)"""
    try:
        from src.tools.session_db import save_session_history as sqlite_save

        return sqlite_save(messages, summary, session_id)
    except ImportError:
        return _save_session_history_jsonl(messages, summary, session_id)


def _load_session_history(session_id: str) -> str:
    """Load conversation history from SQLite (wrapper for session_db.py)"""
    try:
        from src.tools.session_db import load_session_history as sqlite_load

        return sqlite_load(session_id)
    except ImportError:
        return _load_session_history_jsonl(session_id)


def _list_sessions(limit: int = 10) -> str:
    """List recent sessions from SQLite (wrapper for session_db.py)"""
    try:
        from src.tools.session_db import list_sessions as sqlite_list

        return sqlite_list(limit)
    except ImportError:
        return _list_sessions_jsonl(limit)


def _search_history(keyword: str, limit: int = 20) -> str:
    """Search conversation history using FTS5 (wrapper for session_db.py)"""
    try:
        from src.tools.session_db import search_history as sqlite_search

        return sqlite_search(keyword, limit)
    except ImportError:
        return _search_history_jsonl(keyword, limit)


# ---- JSONL Fallback (保留向后兼容) ----


def _generate_session_filename() -> str:
    """生成会话文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"session_{timestamp}.jsonl"


def _save_session_history_jsonl(
    messages: list, summary: str | None = None, session_id: str | None = None
) -> str:
    """JSONL fallback implementation"""
    try:
        _ensure_sessions_dir()
        if not session_id:
            session_id = _generate_session_filename()
        filepath = os.path.join(SESSIONS_DIR, session_id)
        with open(filepath, "a", encoding="utf-8") as f:
            if not os.path.exists(filepath) or os.stat(filepath).st_size == 0:
                meta = {
                    "type": "session_meta",
                    "session_id": session_id,
                    "created_at": datetime.now().isoformat(),
                }
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for msg in messages:
                msg["timestamp"] = datetime.now().isoformat()
                msg["type"] = "message"
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            if summary:
                summary_line = {
                    "type": "summary",
                    "content": summary,
                    "timestamp": datetime.now().isoformat(),
                }
                f.write(json.dumps(summary_line, ensure_ascii=False) + "\n")
        msg_count = len(messages)
        return f"Session saved: {session_id} ({msg_count} messages)"
    except Exception as e:
        return f"Error saving session: {e!s}"


def _load_session_history_jsonl(session_id: str) -> str:
    """JSONL fallback implementation"""
    try:
        filepath = os.path.join(SESSIONS_DIR, session_id)
        if not os.path.exists(filepath):
            matches = [
                f
                for f in os.listdir(SESSIONS_DIR)
                if f.startswith(session_id) or session_id in f
            ]
            if matches:
                filepath = os.path.join(SESSIONS_DIR, matches[0])
            else:
                return f"Session not found: {session_id}"
        messages = []
        meta = {}
        summary = None
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("type") == "session_meta":
                    meta = obj
                elif obj.get("type") == "message":
                    messages.append(obj)
                elif obj.get("type") == "summary":
                    summary = obj.get("content")
        output = f"Session: {meta.get('session_id', session_id)}\n"
        output += f"Created: {meta.get('created_at', 'unknown')}\n"
        output += f"Messages: {len(messages)}\n"
        if summary:
            output += f"Summary: {summary}\n"
        output += "---\n"
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if msg.get("tool_calls"):
                tc_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in msg["tool_calls"]
                ]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            if msg.get("tool_call_id"):
                content = msg.get("content", "")[:200]
            if len(content) > 500:
                content = content[:500] + "..."
            output += f"{role}: {content}\n"
        return output
    except Exception as e:
        return f"Error loading session: {e!s}"


def _list_sessions_jsonl(limit: int = 10) -> str:
    """JSONL fallback implementation"""
    try:
        _ensure_sessions_dir()
        files = sorted(os.listdir(SESSIONS_DIR), reverse=True)
        session_files = [
            f for f in files if f.startswith("session_") and f.endswith(".jsonl")
        ]
        results = []
        for f in session_files[:limit]:
            filepath = os.path.join(SESSIONS_DIR, f)
            msg_count = 0
            created_at = "unknown"
            summary = None
            with open(filepath, encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("type") == "session_meta":
                        created_at = obj.get("created_at", "unknown")
                    elif obj.get("type") == "message":
                        msg_count += 1
                    elif obj.get("type") == "summary":
                        summary = obj.get("content", "")[:100]
            results.append(
                {
                    "session_id": f,
                    "created_at": created_at,
                    "message_count": msg_count,
                    "summary": summary,
                }
            )
        if not results:
            return "No sessions found."
        output = "Recent Sessions:\n"
        for s in results:
            output += (
                f"- {s['session_id']}: {s['message_count']} msgs, {s['created_at']}\n"
            )
            if s["summary"]:
                output += f"  Summary: {s['summary']}...\n"
        return output
    except Exception as e:
        return f"Error listing sessions: {e!s}"


def _search_history_jsonl(keyword: str, limit: int = 20) -> str:
    """JSONL fallback implementation"""
    try:
        _ensure_sessions_dir()
        files = [
            f
            for f in os.listdir(SESSIONS_DIR)
            if f.startswith("session_") and f.endswith(".jsonl")
        ]
        results = []
        keyword_lower = keyword.lower()
        for f in files:
            filepath = os.path.join(SESSIONS_DIR, f)
            messages = []
            with open(filepath, encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("type") == "message":
                        messages.append(obj)
            for i, msg in enumerate(messages):
                content = msg.get("content", "")
                if content and keyword_lower in content.lower():
                    context_start = max(0, i - 1)
                    context_end = min(len(messages), i + 2)
                    context = messages[context_start:context_end]
                    results.append(
                        {
                            "session_id": f,
                            "timestamp": msg.get("timestamp", "unknown"),
                            "role": msg.get("role"),
                            "matched": content[:300] + "..."
                            if len(content) > 300
                            else content,
                            "context": [
                                f"{m.get('role')}: {m.get('content', '')[:100]}"
                                for m in context
                            ],
                        }
                    )
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break
        if not results:
            return f"No matches found for: {keyword}"
        output = f"Found {len(results)} matches for '{keyword}':\n"
        for r in results:
            output += f"\n[{r['session_id']}] {r['timestamp']}\n"
            output += f"{r['role']}: {r['matched']}\n"
            output += f"Context: {r['context']}\n"
        return output
    except Exception as e:
        return f"Error searching history: {e!s}"


# ==================== Memory Graph 工具 (SQLite 后端) ====================


def _record_skill_outcome(
    skill_name: str,
    outcome: str,
    score: float = 1.0,
    signals: list | None = None,
    session_id: str | None = None,
    context: str | None = None,
) -> str:
    """
    Record skill execution outcome to gene_outcomes table.

    Called after skill execution completes:
    - AgentLoop: after tool execution iteration
    - AutonomousExplorer: after autonomous task completion
    - RalphLoop: after cycle completion

    Args:
        skill_name: Skill identifier
        outcome: 'success' | 'failed' | 'partial'
        score: 0.0 - 1.0 (granular success measure)
        signals: Trigger signal patterns (list of strings)
        session_id: Links to session_messages table
        context: Optional execution context summary

    Returns:
        Status message with updated statistics
    """
    try:
        from src.tools.session_db import record_skill_outcome as db_record

        return db_record(skill_name, outcome, score, signals, session_id, context)
    except ImportError:
        return "Error: session_db module not available"


def _get_skill_stats(skill_name: str) -> str:
    """
    Get aggregated outcome statistics for a skill.

    Returns formatted string with:
    - total attempts, successes, failures
    - success rate, Laplace-smoothed rate
    - recent success rate (last 30 days)
    - is_banned status, selection value
    """
    try:
        from src.tools.session_db import get_skill_stats as db_stats

        stats = db_stats(skill_name)
        if "error" in stats:
            return f"Error: {stats['error']}"

        output = f"Skill Statistics: {skill_name}\n"
        output += f"- Total attempts: {stats['total']}\n"
        output += f"- Successes: {stats['successes']}, Failures: {stats['failures']}\n"
        output += f"- Success rate: {stats['success_rate']:.1%}\n"
        output += f"- Laplace rate: {stats['laplace_rate']:.1%}\n"
        output += f"- Recent rate (30d): {stats['recent_success_rate']:.1%}\n"
        output += f"- Selection value: {stats['selection_value']:.3f}\n"
        output += f"- Banned: {stats['is_banned']}\n"
        if stats["last_success"]:
            output += f"- Last success: {stats['last_success']}\n"
        if stats["last_failure"]:
            output += f"- Last failure: {stats['last_failure']}\n"
        return output
    except ImportError:
        return "Error: session_db module not available"


def _list_banned_skills() -> str:
    """
    List skills with value below ban_threshold.

    Returns formatted list with:
    - skill_name, total_attempts, current_value
    - success_rate, ban_reason, suggested_action
    """
    try:
        from src.tools.session_db import list_banned_skills as db_list

        banned = db_list()
        if not banned:
            return "No banned skills found."

        output = "Banned Skills:\n"
        for s in banned:
            output += f"\n- {s['skill_name']}\n"
            output += (
                f"  Attempts: {s['total_attempts']}, Value: {s['current_value']:.3f}\n"
            )
            output += f"  Success rate: {s['success_rate']:.1%}\n"
            output += f"  Reason: {s['ban_reason']}\n"
            output += f"  Action: {s['suggested_action']}\n"
        return output
    except ImportError:
        return "Error: session_db module not available"


def _get_top_skills(limit: int = 10) -> str:
    """
    Get top skills by selection value.

    Args:
        limit: Maximum number to return

    Returns:
        Formatted list of top skills
    """
    try:
        from src.tools.session_db import get_top_skills as db_top

        top = db_top(limit)
        if not top:
            return "No skills with outcome history found."

        output = f"Top {len(top)} Skills (by selection value):\n"
        for s in top:
            output += f"\n- {s['skill_name']}\n"
            output += (
                f"  Value: {s['selection_value']:.3f}, Rate: {s['success_rate']:.1%}\n"
            )
            output += f"  Attempts: {s['total']}\n"
        return output
    except ImportError:
        return "Error: session_db module not available"


# ==================== L4 用户建模工具 (黑格尔辩证式进化) ====================


def _observe_user_preference(
    key: str, value: str, context: str | None = None, confidence: float = 0.8
) -> str:
    """
    观察用户偏好证据

    Args:
        key: 偏好键 (如 "coffee", "work_style")
        value: 偏好值
        context: 观察上下文 (如 "周三下午")
        confidence: 置信度 (0.0-1.0)

    Returns:
        观察记录状态

    Example:
        observe_user_preference("coffee", "美式", confidence=0.9)
        observe_user_preference("coffee", "拿铁", context="周三下午", confidence=0.85)
    """
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.observe(
            evidence_type="preference",
            data={"key": key, "value": value},
            context=context,
            confidence=confidence,
        )
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error observing preference: {type(e).__name__}: {str(e)[:100]}"


def _get_user_preference(key: str, context: str | None = None) -> str:
    """
    获取用户偏好（基于上下文）

    Args:
        key: 偏好键
        context: 当前上下文 (用于检查例外情况)

    Returns:
        基于上下文的偏好值和推理说明

    Example:
        get_user_preference("coffee") -> "美式 (常规偏好)"
        get_user_preference("coffee", "周三下午") -> "拿铁 (例外情况: 周三下午)"
    """
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        result = user_model.get_user_preference(key, context)

        output = f"用户偏好 '{key}':\n"
        output += f"- 值: {result['value']}\n"
        output += f"- 原因: {result['reason']}\n"
        output += f"- 置信度: {result['confidence']:.2f}\n"
        return output
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error getting preference: {type(e).__name__}: {str(e)[:100]}"


def _get_user_profile_summary() -> str:
    """
    获取用户画像完整摘要

    Returns:
        所有偏好的摘要，包括例外情况

    Example:
        用户画像摘要:
        - coffee: 平时 美式, 例外情况 周三下午: 拿铁
        - work_style: 深度工作模式
    """
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.get_user_profile_summary()
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error getting profile: {type(e).__name__}: {str(e)[:100]}"


def _update_user_model() -> str:
    """
    触发用户模型辩证式更新

    注意: 此函数为异步操作，在同步环境中返回提示信息

    Returns:
        更新提示信息 (实际更新需要在异步环境中执行)
    """
    return (
        "提示: 用户模型辩证式更新需要异步执行。\n"
        "请使用 MemoryManager.update_user_model() 在异步环境中调用。\n"
        "流程: 检测矛盾 -> 内部推理 -> 升级模型 (不覆盖)"
    )


def _list_user_preferences() -> str:
    """
    列出所有用户偏好

    Returns:
        所有偏好的键值列表
    """
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        preferences = user_model.get_all_preferences()

        if not preferences:
            return "无用户偏好记录"

        output = "用户偏好列表:\n"
        for key, pref_data in preferences.items():
            usual = pref_data.get("usual", "未知")
            exceptions = pref_data.get("exceptions", {})
            confidence = pref_data.get("confidence", 0.0)

            output += f"\n- {key}: {usual} (置信度 {confidence:.2f})\n"
            if exceptions:
                for exc_key, exc_val in exceptions.items():
                    if exc_key != "previously":
                        output += (
                            f"  例外 [{exc_key}]: {exc_val.get('value', '未知')}\n"
                        )

        return output
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error listing preferences: {type(e).__name__}: {str(e)[:100]}"


# ==================== L5 工作日志工具 (长期归档 + LLM摘要) ====================


def _archive_session_events(
    session_id: str, events_json: str, metadata_json: str | None = None
) -> str:
    """
    归档会话事件到长期存储

    注意: 此函数为异步操作，在同步环境中返回提示信息

    Args:
        session_id: 会话 ID
        events_json: JSON 格式的事件列表
        metadata_json: JSON 格式的元数据

    Returns:
        归档提示信息 (实际归档需要在异步环境中执行)
    """
    try:
        import json

        events = json.loads(events_json) if events_json else []

        if not events:
            return "Error: No events to archive"

        return (
            f"提示: 会话归档需要异步执行。\n"
            f"请使用 MemoryManager.archive_session() 在异步环境中调用。\n"
            f"会话 ID: {session_id}, 事件数: {len(events)}"
        )
    except json.JSONDecodeError as e:
        return f"Error parsing JSON: {type(e).__name__}: {str(e)[:100]}"


def _search_archives(keyword: str, limit: int = 20) -> str:
    """
    搜索归档内容 (FTS5 全文检索)

    Args:
        keyword: 搜索关键词
        limit: 结果限制

    Returns:
        匹配的归档列表，包含摘要和关键发现

    Example:
        search_archives("重构") -> 返回包含"重构"关键词的归档
    """
    try:
        from src.tools.long_term_archive import LongTermArchiveLayer

        archive = LongTermArchiveLayer()
        results = archive.search_with_context(keyword, limit)

        if not results:
            return f"未找到匹配 '{keyword}' 的归档"

        output = f"找到 {len(results)} 个匹配 '{keyword}' 的归档:\n"
        for r in results:
            output += f"\n[{r['archive_id']}]\n"
            output += f"- 会话: {r['session_id']}\n"
            output += f"- 摘要: {r['summary'][:100]}...\n"
            output += f"- 匹配片段: {r['matched_snippet'][:50]}...\n"
            if r["key_findings"]:
                output += f"- 关键发现: {r['key_findings'][0]}\n"
            output += f"- 时间: {r['timestamp']}\n"

        return output
    except ImportError:
        return "Error: long_term_archive module not available"
    except Exception as e:
        return f"Error searching archives: {type(e).__name__}: {str(e)[:100]}"


def _get_archive_details(archive_id: str) -> str:
    """
    获取归档详情

    Args:
        archive_id: 归档 ID

    Returns:
        归档完整信息，包括摘要、关键发现和事件列表
    """
    try:
        from src.tools.long_term_archive import LongTermArchiveLayer

        archive = LongTermArchiveLayer()
        details = archive.get_archive(archive_id)

        if not details:
            return f"归档不存在: {archive_id}"

        output = f"归档详情: {archive_id}\n"
        output += f"- 会话 ID: {details['session_id']}\n"
        output += f"- 创建时间: {details['created_at']}\n"
        output += f"- 事件数: {details['events_count']}\n"
        output += f"- 摘要: {details['summary']}\n"

        if details["key_findings"]:
            output += "- 关键发现:\n"
            for finding in details["key_findings"]:
                output += f"  * {finding}\n"

        if details["events"]:
            output += "- 事件概览 (前5个):\n"
            for event in details["events"][:5]:
                output += f"  [{event['type']}] {str(event['data'])[:50]}...\n"

        return output
    except ImportError:
        return "Error: long_term_archive module not available"
    except Exception as e:
        return f"Error getting archive: {type(e).__name__}: {str(e)[:100]}"


def _get_archive_stats() -> str:
    """
    获取归档统计信息

    Returns:
        归档总数、事件总数、平均事件数、最近归档列表
    """
    try:
        from src.tools.long_term_archive import LongTermArchiveLayer

        archive = LongTermArchiveLayer()
        stats = archive.get_archive_stats()

        output = "L5 归档统计:\n"
        output += f"- 总归档数: {stats['total_archives']}\n"
        output += f"- 总事件数: {stats['total_events']}\n"
        output += f"- 平均事件数/归档: {stats['avg_events_per_archive']}\n"

        if stats["recent_archives"]:
            output += "- 最近归档:\n"
            for a in stats["recent_archives"]:
                output += f"  [{a['archive_id']}] {a['events_count']} 事件, {a['created_at']}\n"

        return output
    except ImportError:
        return "Error: long_term_archive module not available"
    except Exception as e:
        return f"Error getting stats: {type(e).__name__}: {str(e)[:100]}"


def _get_memory_hierarchy() -> str:
    """
    获取五层记忆架构摘要

    Returns:
        L1-L5 各层的统计信息
    """
    try:
        from src.memory_manager import get_memory_manager

        manager = get_memory_manager()
        return manager.get_memory_hierarchy_summary()
    except ImportError:
        return "Error: memory_manager module not available"
    except Exception as e:
        return f"Error getting hierarchy: {type(e).__name__}: {str(e)[:100]}"
