"""
Ralph Loop 工厂方法模块

提供工厂方法：
- create_test_driven: 创建测试驱动的 Ralph Loop
- create_marker_driven: 创建标志文件驱动的 Ralph Loop
- create_ralph_loop: 异步创建 Ralph Loop
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.ralph_core import CompletionType
from src.shared_config import get_seed_dir_with_fallback

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop
    from src.ralph_loop import RalphLoop

logger = logging.getLogger("seed_agent.ralph")


class FactoryMixin:
    """Ralph Loop 工厂方法功能 Mixin"""

    @classmethod
    def create_test_driven(
        cls: type["RalphLoop"],
        agent_loop: "AgentLoop",
        task_prompt_path: Path,
        test_command: str = "pytest tests/ -v",
        pass_rate: float = 100,
    ) -> "RalphLoop":
        """创建测试驱动的 Ralph Loop"""
        return cls(
            agent_loop=agent_loop,
            completion_type=CompletionType.TEST_PASS,
            completion_criteria={"test_command": test_command, "pass_rate": pass_rate},
            task_prompt_path=task_prompt_path,
        )

    @classmethod
    def create_marker_driven(
        cls: type["RalphLoop"],
        agent_loop: "AgentLoop",
        task_prompt_path: Path,
        marker_path: Path | None = None,
        marker_content: str = "DONE",
    ) -> "RalphLoop":
        """创建标志文件驱动的 Ralph Loop"""
        return cls(
            agent_loop=agent_loop,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={
                "marker_path": str(marker_path or get_seed_dir_with_fallback() / "completion_marker"),
                "marker_content": marker_content,
            },
            task_prompt_path=task_prompt_path,
        )


async def create_ralph_loop(
    agent_loop: "AgentLoop",
    task_file: str,
    completion_type: str = "marker_file",
    completion_criteria: dict | None = None,
    **kwargs,
) -> "RalphLoop":
    """创建 Ralph Loop 实例"""
    from src.ralph_loop import RalphLoop

    type_map = {
        "test_pass": CompletionType.TEST_PASS,
        "file_exists": CompletionType.FILE_EXISTS,
        "marker_file": CompletionType.MARKER_FILE,
        "git_clean": CompletionType.GIT_CLEAN,
        "custom_check": CompletionType.CUSTOM_CHECK,
    }

    c_type = type_map.get(completion_type, CompletionType.MARKER_FILE)
    criteria = completion_criteria or {}

    task_path = Path(task_file)
    if not task_path.is_absolute():
        task_path = get_seed_dir_with_fallback() / "tasks" / task_file

    return RalphLoop(
        agent_loop=agent_loop,
        completion_type=c_type,
        completion_criteria=criteria,
        task_prompt_path=task_path,
        **kwargs,
    )


__all__ = ["FactoryMixin", "create_ralph_loop"]