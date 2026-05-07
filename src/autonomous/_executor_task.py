"""任务执行主方法模块

包含 execute_autonomous_task 核心逻辑。
"""

import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.autonomous._defense import DefenseState
from src.autonomous._executor_helpers import notify_completion
from src.autonomous._prompt_builder import build_autonomous_prompt, extract_task_signals
from src.autonomous._ralph_loop import run_ralph_loop
from src.autonomous._sop_loader import expand_sop_paths
from src.autonomous._state_manager import StateManager, TodoCache
from src.session_event_stream import EventType

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent")


async def execute_autonomous_task(
    agent: "AgentLoop",
    state_manager: StateManager,
    todo_cache: TodoCache,
    defense: DefenseState,
    sop_content: str | None,
    seed_dir: Path,
    config: Any,
    on_explore_complete: Callable[[str], None] | Callable[[str], Coroutine[Any, Any, None]] | None,
) -> str | None:
    """执行自主探索任务

    Args:
        agent: AgentLoop 实例
        state_manager: 状态管理器
        todo_cache: TODO 缓存
        defense: 四层防御状态
        sop_content: SOP 内容
        seed_dir: Seed 目录
        config: 配置对象
        on_explore_complete: 探索完成回调

    Returns:
        str | None: 探索结果文本，失败时返回 None
    """
    if not sop_content:
        logger.warning("No SOP loaded, skipping autonomous exploration")
        return None

    state_manager.load_or_init_state()

    max_iterations = defense.get_retry_budget()
    if max_iterations == 0:
        logger.warning(
            f"Retry count {defense.get_retry_count()} exceeds max "
            f"{config.max_retry_count}, stopping"
        )
        return None

    defense.reset()
    todo_content = todo_cache.load_todo_content(seed_dir)
    expand_sop_paths(sop_content, seed_dir)

    prompt = build_full_prompt(agent, sop_content, todo_content, seed_dir)

    agent.session.emit_event(
        EventType.SESSION_START,
        {
            "type": "autonomous_exploration",
            "iteration": state_manager.get_iteration_count(),
            "retry_count": defense.get_retry_count(),
            "max_iterations_budget": max_iterations,
            "todo_status": bool(todo_content),
        },
    )

    logger.info(
        f"Starting autonomous exploration: budget={max_iterations}, "
        f"retry={defense.get_retry_count()}"
    )

    original_system_prompt = agent.system_prompt
    original_max_iterations = agent.max_iterations

    agent.set_autonomous_mode(enabled=True, skip_response=config.ask_user_skip_response)

    try:
        agent.system_prompt = prompt
        agent.max_iterations = max_iterations

        # 创建临时 executor 供 ralph_loop 使用
        from src.autonomous._executor_core import TaskExecutor
        temp_executor = TaskExecutor.__new__(TaskExecutor)
        temp_executor.agent = agent
        temp_executor._state_manager = state_manager
        temp_executor._defense = defense
        temp_executor._seed_dir = seed_dir
        temp_executor._sop_content = sop_content
        temp_executor.on_explore_complete = on_explore_complete
        temp_executor._config = config

        response = await run_ralph_loop(temp_executor, max_iterations)

        if response:
            logger.info(f"Autonomous exploration completed, response length: {len(response)}")
            agent.session.emit_event(
                EventType.SESSION_END,
                {
                    "type": "autonomous_exploration",
                    "reason": "completed",
                    "response_length": len(response),
                    "iterations_used": state_manager.get_iteration_count(),
                },
            )
            defense.reset_retry()
            await notify_completion(temp_executor, response)
            return response

        defense.increment_retry()
        logger.warning(f"Autonomous exploration empty, retry_count now {defense.get_retry_count()}")
        agent.session.emit_event(
            EventType.SESSION_END,
            {"type": "autonomous_exploration", "reason": "empty_response", "retry_count": defense.get_retry_count()},
        )
        return None

    except Exception as e:
        logger.exception("Autonomous exploration failed")
        state_manager.persist_state(str(e))
        defense.increment_retry()
        agent.session.emit_event(
            EventType.ERROR_OCCURRED,
            {"error_type": "autonomous_exploration_failed", "error_message": str(e)[:500], "retry_count": defense.get_retry_count()},
        )
        return None

    finally:
        agent.set_autonomous_mode(enabled=False)
        agent.system_prompt = original_system_prompt
        agent.max_iterations = original_max_iterations


def build_full_prompt(agent: "AgentLoop", sop_content: str | None, todo_content: str, seed_dir: Path) -> str:
    """构建完整的自主探索 prompt"""
    base_system_prompt = agent.system_prompt or ""

    skills_prompt = ""
    best_skill = None
    gene_slice = None

    skill_loader = getattr(agent, "skill_loader", None)
    if skill_loader:
        skills_prompt = skill_loader.get_skills_prompt()
        signals = extract_task_signals(todo_content, bool(todo_content))
        best_skill = skill_loader.select_best_skill(
            signals=signals,
            available_tools=getattr(agent.tools, "get_tool_names", lambda: None)(),
        )
        if best_skill:
            gene_slice = skill_loader.get_gene_slice(best_skill)

    expanded_sop = expand_sop_paths(sop_content or "", seed_dir)

    return build_autonomous_prompt(
        base_system_prompt=base_system_prompt,
        skills_prompt=skills_prompt,
        sop_content=expanded_sop,
        todo_content=todo_content,
        has_todo=bool(todo_content),
        seed_dir=seed_dir,
        best_skill=best_skill,
        gene_slice=gene_slice,
    )


__all__ = ["build_full_prompt", "execute_autonomous_task"]