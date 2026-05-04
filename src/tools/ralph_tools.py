"""Ralph Loop 工具注册

提供 Agent 可调用的 Ralph Loop 相关工具:
- start_ralph_loop: 启动 Ralph Loop
- write_completion_marker: 写入完成标志
- check_ralph_status: 检查 Ralph Loop 状态
- stop_ralph_loop: 停止 Ralph Loop

类型安全:
- max_iterations 参数在入口处强制转换为整数
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools import ToolRegistry

from src.shared_config import SEED_DIR
from src.tools.utils import safe_int_convert

logger = logging.getLogger(__name__)

# 类型注解使用内置类型

COMPLETION_PROMISE_FILE = SEED_DIR / "completion_promise"
RALPH_STATE_DIR = SEED_DIR / "ralph"

# 兼容别名（使用 utils.py 的公共函数）
_safe_int_convert = safe_int_convert


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
    safe_max_iterations = _safe_int_convert(max_iterations, default=1000, min_val=1)

    # 解析任务文件路径
    task_path = Path(task_prompt_file)
    if not task_path.is_absolute():
        task_path = SEED_DIR / "tasks" / task_prompt_file

    # 确保任务目录存在
    task_path.parent.mkdir(parents=True, exist_ok=True)

    # 验证任务文件存在
    if not task_path.exists():
        return f"Error: Task file not found - {task_path}"

    # 生成 Ralph Loop ID
    ralph_id = f"ralph_{task_path.stem}"

    # 保存 Ralph Loop 配置
    RALPH_STATE_DIR.mkdir(parents=True, exist_ok=True)
    config_file = RALPH_STATE_DIR / f"{ralph_id}_config.json"

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


def write_completion_marker(
    content: str = "DONE", marker_path: str | None = None
) -> str:
    """写入完成标志（用于 Ralph Loop 的 marker_file 完成验证）

    当 Agent 完成任务后，调用此工具写入完成标志。
    Ralph Loop 会检测到此标志并退出循环。

    Args:
        content: 标志内容（默认 "DONE"，支持 "COMPLETE", "TASK_FINISHED"）
        marker_path: 标志文件路径（默认 ~/.seed/completion_promise）

    Returns:
        成功消息

    Example:
        write_completion_marker("DONE")  # 使用默认路径
        write_completion_marker("COMPLETE", ".seed/custom_marker")  # 自定义路径
    """
    # 解析路径
    if marker_path:
        path = Path(marker_path)
        if not path.is_absolute():
            path = SEED_DIR / marker_path
    else:
        path = COMPLETION_PROMISE_FILE

    # 确保目录存在并写入标志
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    except OSError as e:
        return f"Error: Failed to write completion marker - {type(e).__name__}: {str(e)[:100]}"

    return f"Completion marker written: {path} -> {content}"


def check_ralph_status(ralph_id: str | None = None) -> str:
    """检查 Ralph Loop 状态

    Args:
        ralph_id: Ralph Loop ID（可选，不提供时列出所有）

    Returns:
        Ralph Loop 状态信息

    Example:
        check_ralph_status()  # 列出所有 Ralph Loops
        check_ralph_status("ralph_refactor_auth")  # 查看特定状态
    """
    if not RALPH_STATE_DIR.exists():
        return "No Ralph Loops found"

    if ralph_id:
        # 查找特定 Ralph Loop
        state_file = RALPH_STATE_DIR / f"{ralph_id}_state.json"
        config_file = RALPH_STATE_DIR / f"{ralph_id}_config.json"

        if not state_file.exists() and not config_file.exists():
            return f"Ralph Loop not found: {ralph_id}"

        result = f"Ralph Loop: {ralph_id}\n"

        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                result += f"- Iteration: {state.get('iteration', 'N/A')}\n"
                result += f"- Started: {state.get('start_time', 'N/A')}\n"
                result += (
                    f"- Last Response: {state.get('last_response', '')[:100]}...\n"
                )
                result += "- Status: running\n"
            except json.JSONDecodeError as e:
                result += f"- State file corrupted: {str(e)[:50]}\n"

        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())
                result += f"- Task: {config.get('task_file', 'N/A')}\n"
                result += f"- Completion Type: {config.get('completion_type', 'N/A')}\n"
                result += f"- Max Iterations: {config.get('max_iterations', 'N/A')}\n"
            except json.JSONDecodeError as e:
                result += f"- Config file corrupted: {str(e)[:50]}\n"

        return result

    # 列出所有 Ralph Loops
    configs = list(RALPH_STATE_DIR.glob("*_config.json"))
    states = list(RALPH_STATE_DIR.glob("*_state.json"))

    if not configs and not states:
        return "No Ralph Loops found"

    result = "Ralph Loops:\n"

    for config_file in configs:
        try:
            config = json.loads(config_file.read_text())
            ralph_id = config.get("ralph_id", config_file.stem.replace("_config", ""))
            state_file = RALPH_STATE_DIR / f"{ralph_id}_state.json"

            status = "pending"
            iteration = "N/A"

            if state_file.exists():
                status = "running"
                state = json.loads(state_file.read_text())
                iteration = state.get("iteration", "N/A")

            result += f"- {ralph_id}: {status} (iteration: {iteration})\n"
        except Exception as e:
            result += f"- {config_file.stem}: error reading config ({e})\n"

    return result


def stop_ralph_loop(ralph_id: str) -> str:
    """停止 Ralph Loop

    Args:
        ralph_id: Ralph Loop ID

    Returns:
        操作结果
    """
    state_file = RALPH_STATE_DIR / f"{ralph_id}_state.json"
    config_file = RALPH_STATE_DIR / f"{ralph_id}_config.json"

    if not state_file.exists() and not config_file.exists():
        return f"Ralph Loop not found: {ralph_id}"

    # 更新配置状态
    if config_file.exists():
        config = json.loads(config_file.read_text())
        config["status"] = "stopped"
        config_file.write_text(json.dumps(config, indent=2))

    # 保留状态文件（用于恢复）
    return f"Ralph Loop {ralph_id} stopped. State preserved for potential recovery."


def create_ralph_task_file(task_name: str, task_description: str) -> str:
    """创建 Ralph Loop 任务描述文件

    Args:
        task_name: 任务名称（用于文件名）
        task_description: 任务详细描述

    Returns:
        任务文件路径
    """
    tasks_dir = SEED_DIR / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_file = tasks_dir / f"{task_name}.md"
    task_file.write_text(task_description)

    return f"Task file created: {task_file}"


def register_ralph_tools(registry: "ToolRegistry") -> None:
    """注册 Ralph Loop 工具"""
    registry.register("start_ralph_loop", start_ralph_loop)
    registry.register("write_completion_marker", write_completion_marker)
    registry.register("check_ralph_status", check_ralph_status)
    registry.register("stop_ralph_loop", stop_ralph_loop)
    registry.register("create_ralph_task_file", create_ralph_task_file)
