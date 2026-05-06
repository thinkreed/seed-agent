"""一脑多手编排器 - 聚合模块

处理结果聚合逻辑。
"""

import json
import logging

from src.llm_client import LLMClient

logger = logging.getLogger(__name__)


class MultiHandAggregator:
    """多环境结果聚合器"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def aggregate_results(self, results: dict[str, list[str]]) -> dict:
        """聚合结果"""
        prompt = f"""请分析以下多环境执行结果并给出总结:

执行结果:
{json.dumps(results, ensure_ascii=False, indent=2)}

请输出:
1. 各环境执行情况总结
2. 发现的问题和差异
3. 最终结论和建议
"""

        try:
            response = await self.llm_client.reason([{"role": "user", "content": prompt}])
            summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            return {
                "summary": summary,
                "environments_count": len(results),
                "total_tasks": sum(len(r) for r in results.values()),
            }
        except Exception as e:
            logger.exception("Aggregation failed")
            return {
                "summary": f"Aggregation failed: {e}",
                "environments_count": len(results),
            }