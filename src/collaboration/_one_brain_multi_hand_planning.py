"""一脑多手编排器 - 规划模块

处理多环境任务分配的规划逻辑。
"""

import json
import logging

from src.llm_client import LLMClient

logger = logging.getLogger(__name__)


class MultiHandPlanner:
    """多环境任务规划器"""

    def __init__(self, llm_client: LLMClient, sandbox_count: int, sandbox_labels: dict[int, str]):
        self.llm_client = llm_client
        self._sandbox_count = sandbox_count
        self._sandbox_labels = sandbox_labels

    async def plan_for_multi_hand(self, task: str) -> dict[str, list[dict]]:
        """规划多环境任务分配"""
        sandbox_descriptions = [
            self._sandbox_labels.get(i, f"Sandbox {i}")
            for i in range(self._sandbox_count)
        ]
        env_list = "\n".join(f"- {desc}" for desc in sandbox_descriptions)

        prompt = f"""请为以下任务规划多环境执行方案:

任务: {task}

可用环境:
{env_list}

请输出 JSON 格式的任务分配:
 {{
    "0": [{{"tool": "工具名", "args": {{ "参数": "值"}}}}],
    "1": [{{"tool": "工具名", "args": {{ "参数": "值"}}}}]
}}
"""

        try:
            response = await self.llm_client.reason([{"role": "user", "content": prompt}])
            plan_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._parse_plan(plan_text)
        except Exception as e:
            logger.exception(f"Planning failed: {e}")
            return self._default_plan()

    def _parse_plan(self, plan_text: str) -> dict[str, list[dict]]:
        """解析规划文本"""
        try:
            start = plan_text.find("{")
            end = plan_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(plan_text[start:end])
        except json.JSONDecodeError as e:
            logger.debug(f"Plan JSON parse failed: {e}")

        logger.warning("Failed to parse plan JSON, using default")
        return self._default_plan()

    def _default_plan(self) -> dict[str, list[dict]]:
        """默认分配"""
        return {
            str(i): [{"tool": "code_as_policy", "args": {"code": "execute task"}}]
            for i in range(self._sandbox_count)
        }