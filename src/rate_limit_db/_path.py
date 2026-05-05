"""数据库路径获取

动态获取数据库路径（从 PathsConfig）
"""

from pathlib import Path


def get_db_path() -> Path:
    """获取数据库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().rate_limit_db
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "rate_limit.db"