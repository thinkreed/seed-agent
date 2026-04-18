import os
import re

# 定位项目根目录下的 .seed/memory
# src/tools/memory_tools.py -> 上两级 -> root -> .seed/memory
MEMORY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.seed', 'memory'))

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

def register_memory_tools(registry):
    """Register memory tools to the Agent system."""
    registry.register("write_memory", write_memory)
    registry.register("read_memory_index", read_memory_index)
    registry.register("search_memory", search_memory)