"""SOP 加载模块

提供 SOP（标准操作流程）加载功能:
- load_sop: 加载自主探索 SOP 文件
- expand_sop_paths: 展开 SOP 中的路径变量

从 AutonomousExplorer 中提取，保持接口不变。
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("seed_agent")


# 项目根目录（当前文件所在目录的父目录的父目录）
PROJECT_ROOT = Path(__file__).parent.parent.parent
# SOP 文档路径
SOP_PATH = PROJECT_ROOT / "auto" / "自主探索 SOP.md"


def load_sop() -> str | None:
    """加载自主探索 SOP

    Returns:
        SOP 内容字符串，或 None（文件不存在或读取失败）
    """
    if SOP_PATH.exists():
        try:
            with open(SOP_PATH, encoding="utf-8") as f:
                content = f.read()
            logger.info(f"Loaded autonomous SOP from {SOP_PATH}")
            return content
        except OSError as e:
            logger.warning(f"Failed to read SOP file {SOP_PATH}: {e}")
            return None
    else:
        logger.warning(f"SOP file not found: {SOP_PATH}")
        return None


def expand_sop_paths(
    sop_content: str,
    seed_dir: Path,
) -> str:
    """展开 SOP 中的路径变量

    将 SOP 中的 ~/.seed 替换为实际的 SEED_DIR 绝对路径。

    Args:
        sop_content: SOP 内容
        seed_dir: SEED_DIR 绝对路径

    Returns:
        展开后的 SOP 内容
    """
    if not sop_content:
        return ""

    expanded = sop_content
    seed_dir_str = str(seed_dir)

    # 替换所有 ~/.seed 相关路径
    expanded = expanded.replace("~/.seed", seed_dir_str)
    expanded = expanded.replace("~\\seed", seed_dir_str)

    # 替换 ~ 为用户主目录
    home_dir = os.path.expanduser("~")
    expanded = expanded.replace("~", home_dir)

    return expanded


def get_sop_path() -> Path:
    """获取 SOP 文件路径

    Returns:
        SOP 文件路径
    """
    return SOP_PATH


def get_project_root() -> Path:
    """获取项目根目录

    Returns:
        项目根目录路径
    """
    return PROJECT_ROOT