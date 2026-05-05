"""多智能体协作模块 - 多脑一手编排器

MultiBrainOneHandOrchestrator: 多脑一手编排器

适用场景：多角度分析同一份代码（安全审查 + 性能优化）

核心特性：
- 共享 Sandbox：所有大脑在同一工作台操作
- 多视角分析：每个大脑从不同角度分析
- 协作改进：融合建议后执行改进

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.collaboration._types import AgentInstance, AnalysisResult
from src.llm_client import LLMClient
from src.sandbox import Sandbox

logger = logging.getLogger(__name__)


class MultiBrainOneHandOrchestrator:
    """多脑一手编排器：多个 Claude 共享一个 Sandbox

    适用场景：多角度分析同一份代码（安全审查 + 性能优化）

    核心特性：
    - 共享 Sandbox：所有大脑在同一工作台操作
    - 多视角分析：每个大脑从不同角度分析
    - 协作改进：融合建议后执行改进
    """

    def __init__(
        self,
        sandbox: Sandbox,
        llm_clients: list[LLMClient],
        perspectives: list[str] | None = None,
    ):
        """初始化多脑一手编排器

        Args:
            sandbox: 共享工作台
            llm_clients: 多个 LLMClient（大脑）
            perspectives: 分析视角列表（如 ["security", "performance", "readability"]）
        """
        self.sandbox = sandbox
        self.llm_clients = llm_clients

        # 创建智能体实例
        self._agents: list[AgentInstance] = []
        for i, client in enumerate(llm_clients):
            perspective = (
                perspectives[i]
                if perspectives and i < len(perspectives)
                else f"perspective_{i}"
            )
            self._agents.append(
                AgentInstance(
                    id=str(uuid.uuid4())[:8],
                    llm_client=client,
                    sandbox=sandbox,
                    perspective=perspective,
                )
            )

        self._perspectives: list[str] = perspectives or [
            a.perspective for a in self._agents if a.perspective is not None
        ]
        logger.info(
            f"MultiBrainOneHandOrchestrator initialized: "
            f"brains={len(llm_clients)}, perspectives={self._perspectives}"
        )

    def register_perspective(self, agent_index: int, perspective: str) -> None:
        """为智能体注册分析视角

        Args:
            agent_index: 智能体索引
            perspective: 分析视角
        """
        if agent_index < len(self._agents):
            self._agents[agent_index].perspective = perspective
            self._perspectives[agent_index] = perspective
            logger.debug(
                f"Perspective registered: agent={agent_index}, perspective={perspective}"
            )

    async def analyze_from_multiple_angles(self, target: str) -> dict[str, Any]:
        """多角度分析

        Args:
            target: 分析目标（文件路径或代码片段）

        Returns:
            多角度分析结果
        """
        # 1. 共享 Sandbox 读取目标
        target_content = await self._read_target(target)

        # 2. 每个 Claude 从不同视角分析（并行）
        analysis_tasks = [
            self._analyze_with_perspective(agent, target_content)
            for agent in self._agents
        ]
        analyses = await asyncio.gather(*analysis_tasks)

        # 3. 更新智能体状态
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

    async def _read_target(self, target: str) -> str:
        """读取分析目标

        Args:
            target: 目标路径或内容

        Returns:
            目标内容
        """
        # 如果是文件路径，通过 Sandbox 读取
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

        # 否则直接返回作为代码片段
        return target

    async def _analyze_with_perspective(
        self,
        agent: AgentInstance,
        content: str,
    ) -> AnalysisResult:
        """从特定视角分析

        Args:
            agent: 智能体实例
            content: 分析内容

        Returns:
            分析结果
        """
        agent.status = "running"
        perspective = agent.perspective or "general"

        prompt = f"""请从 {perspective} 视角分析以下代码/内容:

```
{content[:5000]}  # 截断防止过长
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
            response = await agent.llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            choices = response.get("choices", [])
            if not choices:
                logger.warning(
                    f"Analysis for {perspective}: LLM returned empty choices"
                )
                agent.status = "failed"
                return AnalysisResult(
                    perspective=perspective,
                    result="",
                    issues=[],
                    suggestions=[],
                )
            result_text = choices[0].get("message", {}).get("content", "")

            # 解析结果
            issues = self._parse_issues(result_text)
            suggestions = self._parse_suggestions(result_text)

            return AnalysisResult(
                perspective=perspective,
                result=result_text,
                issues=issues,
                suggestions=suggestions,
            )

        except (ConnectionError, TimeoutError, OSError) as e:
            # 网络/连接错误：可恢复，记录警告
            logger.warning(
                f"Network error during analysis for {perspective}: {type(e).__name__}: {e}"
            )
            agent.status = "failed"
            return AnalysisResult(
                perspective=perspective,
                result="",
                issues=[],
                suggestions=[],
            )
        except (ValueError, KeyError) as e:
            # 数据解析错误：记录警告
            logger.warning(
                f"Parse error during analysis for {perspective}: {type(e).__name__}: {e}"
            )
            agent.status = "failed"
            return AnalysisResult(
                perspective=perspective,
                result="",
                issues=[],
                suggestions=[],
            )
        except RuntimeError:
            # 运行时错误：严重，需要记录并向上传播
            logger.exception(f"Runtime error during analysis for {perspective}")
            agent.status = "failed"
            raise

    def _parse_issues(self, text: str) -> list[str]:
        """解析问题列表"""
        issues = []
        for line in text.split("\n"):
            if line.strip().startswith("- ") or line.strip().startswith("* "):
                issues.append(line.strip()[2:])
            elif "问题" in line or "issue" in line.lower() or "风险" in line:
                issues.append(line.strip())
        return issues[:10]  # 最多 10 条

    def _parse_suggestions(self, text: str) -> list[str]:
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

    async def collaborative_improve(self, target: str) -> dict[str, Any]:
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
        # 1. 多角度分析
        analysis_result = await self.analyze_from_multiple_angles(target)

        # 2. 融合改进建议（由主 Claude 决断）
        merged_suggestions = await self._merge_suggestions(analysis_result)

        # 3. 执行改进
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
        self, analysis_result: dict[str, Any]
    ) -> dict[str, Any]:
        """融合改进建议

        Args:
            analysis_result: 多角度分析结果

        Returns:
            融合后的建议
        """
        # 收集所有建议
        all_suggestions: list[str] = []
        all_issues: list[str] = []

        for analysis in analysis_result.get("analyses", []):
            all_suggestions.extend(analysis.get("suggestions", []))
            all_issues.extend(analysis.get("issues", []))

        # 去重
        unique_suggestions = list(set(all_suggestions))
        unique_issues = list(set(all_issues))

        # 使用第一个大脑进行融合决策
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

    def _parse_actions(self, text: str) -> list[dict[str, str]]:
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
        self, target: str, actions: list[dict[str, str]]
    ) -> dict[str, Any]:
        """执行改进操作

        Args:
            target: 目标文件
            actions: 改进行动列表

        Returns:
            执行结果
        """
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

    def get_agents_status(self) -> list[dict[str, Any]]:
        """获取所有智能体状态"""
        return [
            {
                "id": agent.id,
                "perspective": agent.perspective,
                "status": agent.status,
            }
            for agent in self._agents
        ]
