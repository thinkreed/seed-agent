"""
L4 Session 数据库存储层 (SQLite + FTS5)
替代原有的 JSONL 文件存储，支持中文全文搜索

使用 jieba 进行中文分词预处理，通过 FTS5 实现高效搜索。

Memory Graph 增强:
- gene_outcomes 表: 存储 Skill 执行结果
- FTS5 虚拟表: 信号模式全文搜索
- 选择算法支持: 成功率统计、禁用阈值、Laplace 平滑

模块结构:
- session_db.py: 模块入口，re-export 公共 API
- session/_session_db_class.py: SessionDB 类实现
- session/_module_fns.py: 模块级单例 + 便捷函数
- session/_schema.py: Schema 创建方法
- session/_skill_outcomes.py: Skill 结果方法
- session/_save.py: 保存操作
- session/_load.py: 加载操作
- session/_search.py: 搜索方法
- session/_cleanup.py: 清理方法
"""

from pathlib import Path

from src.tools.fts_utils import sanitize_fts_query as _sanitize_fts_query
from src.tools.fts_utils import tokenize_for_fts5
from src.tools.session._module_fns import (
    _get_db,
    get_skill_stats,
    get_top_skills,
    list_banned_skills,
    list_sessions,
    load_session_history,
    record_skill_outcome,
    save_session_history,
    search_history,
    search_outcomes_by_signal,
)
from src.tools.session._session_db_class import SessionDB, get_db_path

# 模块级路径变量（兼容旧代码）
DB_PATH = None  # 类型: Path | None


def _get_db_path() -> Path:
    """获取数据库路径（动态）- 兼容旧 API"""
    return Path(get_db_path())


def _ensure_db_path() -> Path:
    """确保数据库路径已初始化 - 兼容旧 API"""
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = _get_db_path()
    return DB_PATH


__all__ = [
    "BannedSkillInfo",
    "SessionDB",
    "_ensure_db_path",
    "_get_db",
    "_get_db_path",
    "_sanitize_fts_query",
    "get_skill_stats",
    "get_top_skills",
    "list_banned_skills",
    "list_sessions",
    "load_session_history",
    "record_skill_outcome",
    "save_session_history",
    "search_history",
    "search_outcomes_by_signal",
    "tokenize_for_fts5",
]

# 从 _skill_outcomes.py re-export BannedSkillInfo
from src.tools.session._skill_outcomes import BannedSkillInfo