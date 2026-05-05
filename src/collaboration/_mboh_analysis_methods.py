"""多智能体协作模块 - 多脑一手分析方法

包含多角度分析和视角分析方法。
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.collaboration._mboh_core import MultiBrainOneHandOrchestrator
from src.collaboration._types import AgentInstance, AnalysisResult

logger = logging.getLogger(__name__)


async def analyze_from_multiple_angles(
    self: MultiBrainOneHandOrchestrator, target: str
) -> dict[str, Any]:
    """多角度分析

    Args:
        target: 分析目标（文件路径或代码片段）

    Returns:
        多角度分析结果
    """
    target_content = await self._read_target(target)

    analysis_tasks = [
        self._analyze_with_perspective(agent, target_content)
        for agent in self._agents
    ]
    analyses = await asyncio.gather(*analysis_tasks)

    for agent in self._agents:
        agent.status = "completed"

    return {
        "target": target,
        "analyses": [
            {
                "perspective": agent.perspective or "default",
                "agent_id": agent.id,
                "result": analysis.result,
                "issues": analysis.issues,
                "suggestions": analysis.suggestions,
            }
            for agent, analysis in zip(self._agents, analyses, strict=True)
        ],
        "sandbox_state": self.sandbox.get_status(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def _read_target(self: MultiBrainOneHandOrchestrator, target: str) -> str:
    """读取分析目标"""
    if target.endswith(
        (".py", ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml")
    ):
        result = await self.sandbox.execute_tools(
            [
                {
                    "id": "read_target",
                    "function": {
                        "name": "file_read",
                        "arguments": json.dumps({"file_path": target}),
                    },
                }
            ]
        )
        if result and result[0].get("content"):
            return result[0]["content"]

    return target


async def _analyze_with_perspective(
    self: MultiBrainOneHandOrchestrator,
    agent: AgentInstance,
    content: str,
) -> AnalysisResult:
    """从特定视角分析"""
    agent.status = "running"
    perspective = agent.perspective or "general"

    prompt = f"""请从 {perspective} 视角分析以下代码/内容:

```
{content[:5000]}
```

分析要点:
1. {perspective} 相关问题
2. 潜在风险
3. 改进建议

请用结构化格式输出：
- 问题列表
- 风险等级
- 改进建议
"""

    try:
        response = await agent.llm_client.reason([{"role": "user", "content": prompt}])
        choices = response.get("choices", [])
        if not choices:
            logger.warning(f"Analysis for {perspective}: LLM returned empty choices")
            agent.status = "failed"
            return AnalysisResult(perspective=perspective, result="", issues=[], suggestions=[])

        result_text = choices[0].get("message", {}).get("content", "")
        issues = self._parse_issues(result_text)
        suggestions = self._parse_suggestions(result_text)

        return AnalysisResult(
            perspective=perspective,
            result=result_text,
            issues=issues,
            suggestions=suggestions,
        )

    except (ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"Network error during analysis for {perspective}: {e}")
        agent.status = "failed"
        return AnalysisResult(perspective=perspective, result="", issues=[], suggestions=[])

    except (ValueError, KeyError) as e:
        logger.warning(f"Parse error during analysis for {perspective}: {e}")
        agent.status = "failed"
        return AnalysisResult(perspective=perspective, result="", issues=[], suggestions=[])

    except RuntimeError:
        logger.exception(f"Runtime error during analysis for {perspective}")
        agent.status = "failed"
        raise


def _parse_issues(self: MultiBrainOneHandOrchestrator, text: str) -> list[str]:
    """解析问题列表"""
    issues = []
    for line in text.split("\n"):
        if line.strip().startswith("- ") or line.strip().startswith("* "):
            issues.append(line.strip()[2:])
        elif "问题" in line or "issue" in line.lower() or "风险" in line:
            issues.append(line.strip())
    return issues[:10]


def _parse_suggestions(self: MultiBrainOneHandOrchestrator, text: str) -> list[str]:
    """解析建议列表"""
    suggestions = [
        line.strip()
        for line in text.split("\n")
        if (
            "建议" in line
            or "suggestion" in line.lower()
            or "改进" in line
            or line.strip().startswith("1. ")
            or line.strip().startswith("2. ")
        )
    ]
    return suggestions[:10]