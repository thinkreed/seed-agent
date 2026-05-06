"""Ralph Loop 启动工具

提供 Ralph Loop 启动和任务文件创建功能:
- start_ralph_loop: 启动 Ralph Loop
- create_ralph_task_file: 创建任务描述文件
"""

import json
import logging
from pathlib import Path

from src.shared_config import get_seed_dir_with_fallback
from src.tools.utils import safe_int_convert

from ._completion import _get_ralph_state_dir

logger = logging.getLogger(__name__)


def start_ralph_loop(
    task_prompt_file: str,
    completion_type: str = "marker_file",
    max_iterations: int = 1000,
    completion_criteria: dict | None = None,
) -> str:
    """启动 Ralph Loop（长周期确定性任务执行器）

    Ralph Loop 核心特性:
    - 外部验证驱动完成（测试通过/DONE标志等）
    - 每次迭代新鲜上下文（防止漂移）
    - 状态持久化（可恢复）
    - 防无限循环保护

    Args:
        task_prompt_file: 任务描述文件路径（相对路径从 ~/.seed/tasks/ 解析）
        completion_type: 完成验证类型
            - "marker_file": 完成标志文件（默认）
            - "test_pass": 测试通过率验证
            - "file_exists": 目标文件存在验证
            - "git_clean": Git 工作区干净验证
            - "custom_check": 自定义验证函数
        max_iterations: 最大迭代次数（默认1000，上限8小时）
        completion_criteria: 完成验证条件（根据类型不同）
            - marker_file: {"marker_path": ".seed/done", "marker_content": "DONE"}
            - test_pass: {"test_command": "pytest tests/", "pass_rate": 100}
            - file_exists: {"files": ["output/result.txt"]}
            - git_clean: {"repo_path": "."}

    Returns:
        Ralph Loop 启动状态和 ID

    Example:
        start_ralph_loop(
            task_prompt_file="refactor_auth.md",
            completion_type="marker_file",
            completion_criteria={"marker_path": ".seed/done"}
        )
    """
    # 类型安全转换：max_iterations 必须是正整数
    safe_max_iterations = safe_int_convert(max_iterations, default=1000, min_val=1)

    # 解析任务文件路径
    task_path = Path(task_prompt_file)
    if not task_path.is_absolute():
        task_path = get_seed_dir_with_fallback() / "tasks" / task_prompt_file

    # 确保任务目录存在
    task_path.parent.mkdir(parents=True, exist_ok=True)

    # 验证任务文件存在
    if not task_path.exists():
        return f"Error: Task file not found - {task_path}"

    # 生成 Ralph Loop ID
    ralph_id = f"ralph_{task_path.stem}"

    # 保存 Ralph Loop 配置
    ralph_dir = _get_ralph_state_dir()
    ralph_dir.mkdir(parents=True, exist_ok=True)
    config_file = ralph_dir / f"{ralph_id}_config.json"

    config = {
        "ralph_id": ralph_id,
        "task_file": str(task_path),
        "completion_type": completion_type,
        "max_iterations": safe_max_iterations,
        "completion_criteria": completion_criteria or {},
        "status": "pending",
    }

    try:
        config_file.write_text(json.dumps(config, indent=2))
    except OSError as e:
        return (
            f"Error: Failed to write config file - {type(e).__name__}: {str(e)[:100]}"
        )

    return f"""Ralph Loop configured successfully:
- ID: {ralph_id}
- Task: {task_path}
- Completion: {completion_type}
- Max Iterations: {safe_max_iterations}

To execute, use: check_ralph_status("{ralph_id}") or run Ralph Loop via scheduler.

Note: Ralph Loop requires AgentLoop instance to execute. Use write_completion_marker() to signal completion."""


def create_ralph_task_file(task_name: str, task_description: str) -> str:
    """创建 Ralph Loop 任务描述文件

    Args:
        task_name: 任务名称（用于文件名）
        task_description: 任务详细描述

    Returns:
        任务文件路径
    """
    ralph_dir = _get_ralph_state_dir()
    tasks_dir = ralph_dir.parent / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_file = tasks_dir / f"{task_name}.md"
    task_file.write_text(task_description)

    return f"Task file created: {task_file}"