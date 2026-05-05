"""多智能体协作模块 - 多脑一手改进方法

包含协作改进和融合建议方法。
"""

import json
import logging
from typing import Any

from src.collaboration._mboh_core import MultiBrainOneHandOrchestrator

logger = logging.getLogger(__name__)


async def collaborative_improve(
    self: MultiBrainOneHandOrchestrator, target: str
) -> dict[str, Any]:
    """协作改进

    流程:
    1. 多角度分析
    2. 融合改进建议
    3. 共享 Sandbox 执行改进

    Args:
        target: 改进目标

    Returns:
        改进结果
    """
    from src.collaboration._mboh_analysis_methods import analyze_from_multiple_angles

    analysis_result = await analyze_from_multiple_angles(self, target)

    merged_suggestions = await self._merge_suggestions(analysis_result)

    if merged_suggestions.get("actions"):
        improvement_result = await self._execute_improvements(
            target, merged_suggestions["actions"]
        )
    else:
        improvement_result = {
            "status": "no_actions",
            "message": "No improvement actions suggested",
        }

    return {
        "target": target,
        "analysis": analysis_result,
        "merged_suggestions": merged_suggestions,
        "improvement_result": improvement_result,
    }


async def _merge_suggestions(
    self: MultiBrainOneHandOrchestrator, analysis_result: dict[str, Any]
) -> dict[str, Any]:
    """融合改进建议"""
    all_suggestions: list[str] = []
    all_issues: list[str] = []

    for analysis in analysis_result.get("analyses", []):
        all_suggestions.extend(analysis.get("suggestions", []))
        all_issues.extend(analysis.get("issues", []))

    unique_suggestions = list(set(all_suggestions))
    unique_issues = list(set(all_issues))

    if self._agents:
        merge_prompt = f"""请融合以下多角度分析的建议：

问题汇总:
{json.dumps(unique_issues[:20], ensure_ascii=False, indent=2)}

建议汇总:
{json.dumps(unique_suggestions[:20], ensure_ascii=False, indent=2)}

请输出:
1. 优先级排序的问题（前 5 个）
2. 最关键的改进建议（前 5 个）
3. 可执行的具体行动步骤
"""
        response = await self._agents[0].llm_client.reason(
            [{"role": "user", "content": merge_prompt}]
        )
        merged_text = (
            response.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

        return {
            "merged_text": merged_text,
            "priority_issues": unique_issues[:5],
            "priority_suggestions": unique_suggestions[:5],
            "actions": self._parse_actions(merged_text),
        }

    return {
        "merged_text": "",
        "priority_issues": unique_issues[:5],
        "priority_suggestions": unique_suggestions[:5],
        "actions": [],
    }


def _parse_actions(self: MultiBrainOneHandOrchestrator, text: str) -> list[dict[str, str]]:
    """解析行动步骤"""
    actions = []
    for line in text.split("\n"):
        if "修改" in line or "edit" in line.lower() or "重写" in line:
            actions.append({"type": "edit", "description": line.strip()})
        elif "添加" in line or "add" in line.lower():
            actions.append({"type": "add", "description": line.strip()})
        elif "删除" in line or "delete" in line.lower() or "remove" in line.lower():
            actions.append({"type": "delete", "description": line.strip()})
    return actions[:10]


async def _execute_improvements(
    self: MultiBrainOneHandOrchestrator,
    target: str,
    actions: list[dict[str, str]],
) -> dict[str, Any]:
    """执行改进操作"""
    results = [
        {
            "action": action,
            "status": "suggested",
            "message": f"建议执行: {action['description']}",
        }
        for action in actions
    ]

    return {
        "status": "completed",
        "results": results,
        "note": "实际改进需要用户确认后执行",
    }