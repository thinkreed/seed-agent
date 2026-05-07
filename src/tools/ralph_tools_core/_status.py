"""Ralph Loop 状态管理工具

提供 Ralph Loop 状态查询和停止功能:
- check_ralph_status: 检查 Ralph Loop 状态
- stop_ralph_loop: 停止 Ralph Loop
"""

import json
import logging

from ._completion import _get_ralph_state_dir

logger = logging.getLogger(__name__)


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
    ralph_dir = _get_ralph_state_dir()
    if not ralph_dir.exists():
        return "No Ralph Loops found"

    if ralph_id:
        # 查找特定 Ralph Loop
        state_file = ralph_dir / f"{ralph_id}_state.json"
        config_file = ralph_dir / f"{ralph_id}_config.json"

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
    configs = list(ralph_dir.glob("*_config.json"))
    states = list(ralph_dir.glob("*_state.json"))

    if not configs and not states:
        return "No Ralph Loops found"

    result = "Ralph Loops:\n"

    for config_file in configs:
        try:
            config = json.loads(config_file.read_text())
            ralph_id_found = config.get("ralph_id", config_file.stem.replace("_config", ""))
            state_file = ralph_dir / f"{ralph_id_found}_state.json"

            status = "pending"
            iteration = "N/A"

            if state_file.exists():
                status = "running"
                state = json.loads(state_file.read_text())
                iteration = state.get("iteration", "N/A")

            result += f"- {ralph_id_found}: {status} (iteration: {iteration})\n"
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
    ralph_dir = _get_ralph_state_dir()
    state_file = ralph_dir / f"{ralph_id}_state.json"
    config_file = ralph_dir / f"{ralph_id}_config.json"

    if not state_file.exists() and not config_file.exists():
        return f"Ralph Loop not found: {ralph_id}"

    # 更新配置状态
    if config_file.exists():
        config = json.loads(config_file.read_text())
        config["status"] = "stopped"
        config_file.write_text(json.dumps(config, indent=2))

    # 保留状态文件（用于恢复）
    return f"Ralph Loop {ralph_id} stopped. State preserved for potential recovery."