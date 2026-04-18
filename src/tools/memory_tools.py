import os
import re
import json
from datetime import datetime
from pathlib import Path

# 定位项目根目录下的 .seed/memory
# src/tools/memory_tools.py -> 上两级 -> root -> .seed/memory
MEMORY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.seed', 'memory'))
SESSIONS_DIR = os.path.join(MEMORY_ROOT, 'raw', 'sessions')

def _get_path(level, filename=None):
    mapping = {'L1': 'notes.md', 'L2': 'skills', 'L3': 'knowledge', 'L4': 'raw'}
    if level not in mapping: return None
    base = mapping[level]
    if base.endswith('.md'):
        return os.path.join(MEMORY_ROOT, base)
    if not filename: return None
    return os.path.join(MEMORY_ROOT, base, filename)

def write_memory(level: str, content: str, title: str = "", metadata: str = "") -> str:
    """
    Write memory to L1/L2/L3/L4. Validates content length and structure.
    
    Args:
        level: L1 (Index), L2 (Skill), L3 (Knowledge), L4 (Raw)
        content: Memory content
        title: Memory title or filename (for L2-L4). For L1, it's the section header.
        metadata: Optional metadata (source, date, etc.)
    """
    # SOP Rule Validation:
    # L1 Constraint: Index only, short.
    if level == 'L1' and len(content) > 200:
        return "Error: L1 content exceeds limit (Index only)."
    if level == 'L1' and ("##" in content or "```" in content):
        return "Error: L1 cannot contain detailed steps or code blocks."

    path = _get_path(level, title if not title.endswith(".md") else title)
    if not path: return "Error: Invalid level or missing filename."

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # L1 appends to notes.md; others create/overwrite files
        if level == 'L1':
            mode = 'a'
            with open(path, mode, encoding='utf-8') as f:
                f.write(f"\n## {title}\n")
                f.write(content.strip() + "\n")
            return f"Updated L1 Index: {title}"
        else:
            mode = 'w'
            with open(path, mode, encoding='utf-8') as f:
                if metadata:
                    f.write(f"<!-- {metadata} -->\n")
                f.write(f"# {title}\n")
                f.write(content.strip() + "\n")
            return f"Saved {level} Memory: {os.path.basename(path)}"
    except Exception as e:
        return f"Error writing memory: {str(e)}"

def read_memory_index() -> str:
    """
    Read the global memory index (L1) to find available SOPs or knowledge.
    
    Returns:
        Content of notes.md
    """
    path = _get_path('L1')
    if not os.path.exists(path):
        return "Memory index not found."
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading index: {str(e)}"

def search_memory(keyword: str, levels: list = ["L1", "L2", "L3"]) -> str:
    """
    Search memory by keyword across L1/L2/L3.
    
    Args:
        keyword: Search keyword
        levels: Levels to search (default L1, L2, L3)
        
    Returns:
        List of matching files with levels.
    """
    results = []
    if not os.path.exists(MEMORY_ROOT):
        return "Memory root not found."
        
    for root, dirs, files in os.walk(MEMORY_ROOT):
        if '.git' in root or '__pycache__' in root: continue
        for file in files:
            if file.endswith(('.md', '.txt')):
                # Determine level
                rel = os.path.relpath(root, MEMORY_ROOT)
                lvl = 'Unknown'
                if 'notes' in rel or file == 'notes.md': lvl = 'L1'
                elif 'skills' in rel: lvl = 'L2'
                elif 'knowledge' in rel: lvl = 'L3'
                elif 'raw' in rel: lvl = 'L4'
                
                if lvl in levels:
                    try:
                        fpath = os.path.join(root, file)
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            if keyword.lower() in f.read().lower():
                                results.append(f"[{lvl}] {file}")
                    except: pass
    return "\n".join(results) if results else "No matching memory found."


def start_long_term_update(args, **kwargs):
    """
    Triggered when the agent believes a task is complete. 
    Dynamically reads memory SOP and injects it into the prompt.
    """
    memory_md_path = os.path.join(os.path.dirname(__file__), '..', '..', 'memory', 'memory.md')
    sop_content = "[Error: Unable to load memory.md]"
    try:
        with open(memory_md_path, 'r', encoding='utf-8') as f:
            sop_content = f.read()
    except Exception as e:
        sop_content = f"Error reading SOP: {str(e)}"
    
    return f"""### [经验提炼] 任务即将结束，请提炼并保存本次任务中的有效经验。

以下是必须严格遵守的记忆管理 SOP，请根据 SOP 中的层级定义和约束进行经验提炼：

{ sop_content }

请总结以下内容并使用 `write_memory` 保存：
1. **环境事实/配置**: 经过验证的路径 (相对)、依赖、配置 (Level: L2)。
2. **SOP/技能**: 成功的操作步骤、代码片段、重试策略 (Level: L2)。
3. **避坑/知识**: 失败原因、解决方案、通用规则 (Level: L3)。
4. **用户偏好**: 特定的需求或习惯 (Level: L2)。"""

def register_memory_tools(registry):
    """Register memory tools to the Agent system."""
    registry.register("write_memory", write_memory)
    registry.register("read_memory_index", read_memory_index)
    registry.register("search_memory", search_memory)
    registry.register("start_long_term_update", start_long_term_update)
    # 对话历史工具
    registry.register("save_session_history", save_session_history)
    registry.register("load_session_history", load_session_history)
    registry.register("list_sessions", list_sessions)
    registry.register("search_history", search_history)


# ==================== 对话历史持久化 (L4 Raw - JSONL 格式) ====================

def _ensure_sessions_dir():
    """确保 sessions 目录存在"""
    os.makedirs(SESSIONS_DIR, exist_ok=True)

def _generate_session_filename() -> str:
    """生成会话文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"session_{timestamp}.jsonl"

def save_session_history(messages: list, summary: str = None, session_id: str = None) -> str:
    """
    Save conversation history to L4 raw/sessions in JSONL format.

    Args:
        messages: List of message dicts with role, content, tool_calls, etc.
        summary: Optional session summary (written as separate line).
        session_id: Optional session ID (filename). If None, generates new one.

    Returns:
        Session ID (filename) or error message.
    """
    try:
        _ensure_sessions_dir()

        if not session_id:
            session_id = _generate_session_filename()

        filepath = os.path.join(SESSIONS_DIR, session_id)

        # JSONL: 每行一个 JSON 对象，追加写入
        with open(filepath, 'a', encoding='utf-8') as f:
            # 首次创建时写入元数据行
            if not os.path.exists(filepath) or os.stat(filepath).st_size == 0:
                meta = {
                    'type': 'session_meta',
                    'session_id': session_id,
                    'created_at': datetime.now().isoformat()
                }
                f.write(json.dumps(meta, ensure_ascii=False) + '\n')

            # 写入消息
            for msg in messages:
                msg['timestamp'] = datetime.now().isoformat()
                msg['type'] = 'message'
                f.write(json.dumps(msg, ensure_ascii=False) + '\n')

            # 写入摘要（如果有）
            if summary:
                summary_line = {
                    'type': 'summary',
                    'content': summary,
                    'timestamp': datetime.now().isoformat()
                }
                f.write(json.dumps(summary_line, ensure_ascii=False) + '\n')

        # 统计消息数
        msg_count = len(messages)
        return f"Session saved: {session_id} ({msg_count} messages)"
    except Exception as e:
        return f"Error saving session: {str(e)}"

def load_session_history(session_id: str) -> str:
    """
    Load conversation history from L4 raw/sessions (JSONL format).

    Args:
        session_id: Session filename (e.g., session_20240418_123456.jsonl)

    Returns:
        Formatted session data or error message.
    """
    try:
        filepath = os.path.join(SESSIONS_DIR, session_id)
        if not os.path.exists(filepath):
            # 尝试模糊匹配
            matches = [f for f in os.listdir(SESSIONS_DIR) 
                       if f.startswith(session_id) or session_id in f]
            if matches:
                filepath = os.path.join(SESSIONS_DIR, matches[0])
            else:
                return f"Session not found: {session_id}"

        messages = []
        meta = {}
        summary = None

        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get('type') == 'session_meta':
                    meta = obj
                elif obj.get('type') == 'message':
                    messages.append(obj)
                elif obj.get('type') == 'summary':
                    summary = obj.get('content')

        # 格式化输出
        output = f"Session: {meta.get('session_id', session_id)}\n"
        output += f"Created: {meta.get('created_at', 'unknown')}\n"
        output += f"Messages: {len(messages)}\n"
        if summary:
            output += f"Summary: {summary}\n"
        output += "---\n"

        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if msg.get('tool_calls'):
                tc_names = [tc.get('function', {}).get('name', 'unknown') 
                            for tc in msg['tool_calls']]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            if msg.get('tool_call_id'):
                content = msg.get('content', '')[:200]

            if len(content) > 500:
                content = content[:500] + "..."

            output += f"{role}: {content}\n"

        return output
    except Exception as e:
        return f"Error loading session: {str(e)}"

def list_sessions(limit: int = 10) -> str:
    """
    List recent conversation sessions from L4 raw/sessions.

    Args:
        limit: Max number of sessions to return.

    Returns:
        List of sessions with metadata.
    """
    try:
        _ensure_sessions_dir()
        files = sorted(os.listdir(SESSIONS_DIR), reverse=True)
        session_files = [f for f in files if f.startswith('session_') and f.endswith('.jsonl')]

        results = []
        for f in session_files[:limit]:
            filepath = os.path.join(SESSIONS_DIR, f)
            msg_count = 0
            created_at = 'unknown'
            summary = None

            with open(filepath, 'r', encoding='utf-8') as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get('type') == 'session_meta':
                        created_at = obj.get('created_at', 'unknown')
                    elif obj.get('type') == 'message':
                        msg_count += 1
                    elif obj.get('type') == 'summary':
                        summary = obj.get('content', '')[:100]

            results.append({
                'session_id': f,
                'created_at': created_at,
                'message_count': msg_count,
                'summary': summary
            })

        if not results:
            return "No sessions found."

        output = "Recent Sessions:\n"
        for s in results:
            output += f"- {s['session_id']}: {s['message_count']} msgs, {s['created_at']}\n"
            if s['summary']:
                output += f"  Summary: {s['summary']}...\n"

        return output
    except Exception as e:
        return f"Error listing sessions: {str(e)}"

def search_history(keyword: str, limit: int = 20) -> str:
    """
    Search conversation history by keyword in L4 raw/sessions.

    Args:
        keyword: Search keyword (case-insensitive).
        limit: Max results to return.

    Returns:
        Matching messages with session and context.
    """
    try:
        _ensure_sessions_dir()
        files = [f for f in os.listdir(SESSIONS_DIR) 
                 if f.startswith('session_') and f.endswith('.jsonl')]

        results = []
        keyword_lower = keyword.lower()

        for f in files:
            filepath = os.path.join(SESSIONS_DIR, f)
            messages = []

            with open(filepath, 'r', encoding='utf-8') as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get('type') == 'message':
                        messages.append(obj)

            for i, msg in enumerate(messages):
                content = msg.get('content', '')
                if content and keyword_lower in content.lower():
                    context_start = max(0, i - 1)
                    context_end = min(len(messages), i + 2)
                    context = messages[context_start:context_end]

                    results.append({
                        'session_id': f,
                        'timestamp': msg.get('timestamp', 'unknown'),
                        'role': msg.get('role'),
                        'matched': content[:300] + "..." if len(content) > 300 else content,
                        'context': [
                            f"{m.get('role')}: {m.get('content', '')[:100]}"
                            for m in context
                        ]
                    })

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
        return f"Error searching history: {str(e)}"