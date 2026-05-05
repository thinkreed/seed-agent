"""定时任务执行模块

包含 TaskScheduler 的执行相关方法：
- _execute_task
- _log_task_execution
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.request_queue import RequestPriority
from src.scheduler._storage import get_log_file

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop
    from src.scheduler._task_definition import ScheduledTask

logger = logging.getLogger("seed_agent")


async def execute_task(
    agent: "AgentLoop",
    task: "ScheduledTask",
) -> tuple[bool, str]:
    """执行任务（支持 tool_calls 循环处理）

    使用 LOW 优先级，确保定时任务不会阻塞用户请求。
    用户请求使用 CRITICAL 优先级，会立即执行。

    Args:
        agent: AgentLoop 实例
        task: 要执行的任务

    Returns:
        tuple[bool, str]: (是否成功, 结果文本)
    """
    try:
        if not agent:
            logger.warning(f"No agent available for task {task.task_id}")
            return False, "No agent available"

        # 使用 agent 的 run 处理任务，支持 tool_calls 循环
        # 使用 LOW 优先级，确保定时任务入队等待，不阻塞用户请求
        original_max_iterations = agent.max_iterations

        try:
            # 临时提升迭代次数以支持复杂任务
            agent.max_iterations = max(original_max_iterations, 30)

            # 通过 run 执行任务（自动处理 tool_calls 循环）
            # LOW 优先级会入队等待，让用户请求（CRITICAL）优先执行
            response = await agent.run(
                task.prompt, priority=RequestPriority.LOW
            )

            # 记录执行结果
            if response:
                logger.info(
                    f"Task {task.task_id} completed ({len(response)} chars)"
                )
            else:
                logger.warning(f"Task {task.task_id} returned empty response")

            # 记录执行日志
            result = response[:500] if response else "Empty response"
            return bool(response), result

        finally:
            # 恢复原始迭代限制
            agent.max_iterations = original_max_iterations

    except asyncio.CancelledError:
        logger.info(f"Task {task.task_id} cancelled")
        return False, "Cancelled"
    except TimeoutError as e:
        logger.warning(f"Task {task.task_id} timed out: {e}")
        return False, f"Timeout: {e!s}"
    except Exception as e:
        logger.exception(f"Task {task.task_id} failed")
        return False, f"Error: {e!s}"


def log_task_execution(task: "ScheduledTask", result: str, success: bool) -> None:
    """记录任务执行日志

    Args:
        task: 执行的任务
        result: 执行结果
        success: 是否成功
    """
    log_file = get_log_file()

    log_entry = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "task_id": task.task_id,
        "task_type": task.task_type,
        "success": success,
        "result": result[:500],
    }

    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


__all__ = ["execute_task", "log_task_execution"]