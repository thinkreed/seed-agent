"""一脑多手编排器 - 执行模块

处理 Sandbox 任务执行逻辑。
"""

import json
import logging
import uuid

from src.sandbox import Sandbox

logger = logging.getLogger(__name__)


class MultiHandExecutor:
    """多环境任务执行器"""

    async def execute_sandbox_tasks(
        self, sandbox: Sandbox, tasks: list[dict]
    ) -> list[str]:
        """执行 Sandbox 任务列表"""
        results: list[str] = []

        for task in tasks:
            tool_name = task.get("tool", "code_as_policy")
            tool_args = task.get("args", {})

            try:
                result = await sandbox.execute_tools([
                    {
                        "id": str(uuid.uuid4())[:8],
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args),
                        },
                    }
                ])
                if result:
                    results.append(result[0].get("content", "No content"))
                else:
                    results.append("No result returned")
            except Exception as e:
                logger.exception("Task execution failed")
                results.append(f"Error: {e}")

        return results