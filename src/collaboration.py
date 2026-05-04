"""
多智能体协作模块

基于 Harness Engineering "三件套解耦架构" 设计的三种协作模式：
- 多脑一手：多个 Claude 共享一个 Sandbox
- 一脑多手：一个 Claude 控制多个 Sandbox
- 多脑多手：多个 Claude 各有 Sandbox，通过 Session 协调

核心组件：
- MultiBrainOneHandOrchestrator: 多角度分析同一份代码
- OneBrainMultiHandOrchestrator: 跨环境执行任务
- MultiBrainMultiHandOrchestrator: Session 协调的复杂任务
- InterAgentMessageBus: 智能体间消息传递总线

版本: v2.0 (重写实现)
创建日期: 2026-05-03
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from src.llm_client import LLMClient
from src.sandbox import IsolationLevel, Sandbox
from src.session_event_stream import EventType, SessionEventStream

logger = logging.getLogger(__name__)

# 默认配置
MAX_DYNAMIC_ITERATIONS = 10  # 动态任务分配最大迭代


class CollaborationMode(str, Enum):
    """协作模式枚举"""

    MULTI_BRAIN_ONE_HAND = "multi_brain_one_hand"  # 多脑一手
    ONE_BRAIN_MULTI_HAND = "one_brain_multi_hand"  # 一脑多手
    MULTI_BRAIN_MULTI_HAND = "multi_brain_multi_hand"  # 多脑多手


@dataclass
class AgentInstance:
    """智能体实例"""

    id: str
    llm_client: LLMClient
    sandbox: Sandbox | None = None
    perspective: str | None = None  # 分析视角（多脑一手）
    label: str | None = None  # 工作台标签（一脑多手）
    status: str = "idle"  # idle, running, completed, failed


@dataclass
class AnalysisResult:
    """分析结果"""

    perspective: str
    result: str
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """执行结果"""

    agent_id: str
    label: str
    results: list[str]
    success: bool
    error: str | None = None


@dataclass
class CoordinationResult:
    """协调结果"""

    task: str
    agent_results: list[dict[str, Any]]
    merged_result: dict[str, Any]
    session_events: list[dict[str, Any]]


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
            "timestamp": datetime.now().isoformat(),
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
                logger.warning(f"Analysis for {perspective}: LLM returned empty choices")
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
            logger.warning(f"Network error during analysis for {perspective}: {type(e).__name__}: {e}")
            agent.status = "failed"
            return AnalysisResult(
                perspective=perspective,
                result="",
                issues=[],
                suggestions=[],
            )
        except (ValueError, KeyError) as e:
            # 数据解析错误：记录警告
            logger.warning(f"Parse error during analysis for {perspective}: {type(e).__name__}: {e}")
            agent.status = "failed"
            return AnalysisResult(
                perspective=perspective,
                result="",
                issues=[],
                suggestions=[],
            )
        except RuntimeError as e:
            # 运行时错误：严重，需要记录并向上传播
            logger.error(f"Runtime error during analysis for {perspective}: {e}")
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
        suggestions = []
        for line in text.split("\n"):
            if "建议" in line or "suggestion" in line.lower() or "改进" in line:
                suggestions.append(line.strip())
            elif line.strip().startswith("1. ") or line.strip().startswith("2. "):
                suggestions.append(line.strip())
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
        results = []
        for action in actions:
            # 这里简化处理，实际需要更复杂的代码修改逻辑
            results.append(
                {
                    "action": action,
                    "status": "suggested",
                    "message": f"建议执行: {action['description']}",
                }
            )

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


class OneBrainMultiHandOrchestrator:
    """一脑多手编排器：一个 Claude 控制多个 Sandbox

    适用场景：在不同环境执行任务（Python + Node.js）

    核心特性：
    - 多工作台：每个 Sandbox 代表不同环境
    - 任务分配：大脑规划各环境任务
    - 跨环境测试：同时在不同环境验证
    """

    def __init__(
        self,
        llm_client: LLMClient,
        sandbox_configs: list[dict[str, Any]],
        labels: list[str] | None = None,
    ):
        """初始化一脑多手编排器

        Args:
            llm_client: 单个大脑
            sandbox_configs: Sandbox 配置列表
            labels: 工作台标签（如 ["python_env", "node_env", "browser"]）
        """
        self.llm_client = llm_client

        # 创建多个工作台
        self.sandboxes: list[Sandbox] = []
        self._agents: list[AgentInstance] = []

        for i, config in enumerate(sandbox_configs):
            # 支持字符串和枚举两种输入
            isolation_level_raw = config.get("isolation_level", IsolationLevel.PROCESS)
            if isinstance(isolation_level_raw, str):
                isolation_level = IsolationLevel(isolation_level_raw)
            else:
                isolation_level = isolation_level_raw

            sandbox = Sandbox(
                isolation_level=isolation_level,
                file_system_root=config.get("file_system_root"),
                workspace_path=config.get("workspace_path"),
            )
            self.sandboxes.append(sandbox)

            label = labels[i] if labels and i < len(labels) else f"sandbox_{i}"
            self._agents.append(
                AgentInstance(
                    id=str(uuid.uuid4())[:8],
                    llm_client=llm_client,
                    sandbox=sandbox,
                    label=label,
                )
            )

        self._sandbox_labels: dict[int, str] = {
            i: agent.label or f"sandbox_{i}" for i, agent in enumerate(self._agents)
        }

        logger.info(
            f"OneBrainMultiHandOrchestrator initialized: "
            f"sandboxes={len(self.sandboxes)}, labels={list(self._sandbox_labels.values())}"
        )

    def label_sandbox(self, index: int, label: str) -> None:
        """为 Sandbox 设置标签

        Args:
            index: Sandbox 索引
            label: 标签
        """
        if index < len(self.sandboxes):
            self._sandbox_labels[index] = label
            self._agents[index].label = label
            logger.debug(f"Sandbox labeled: index={index}, label={label}")

    async def execute_in_multiple_environments(self, task: str) -> dict[str, Any]:
        """在不同环境执行任务

        Args:
            task: 任务描述

        Returns:
            各环境执行结果
        """
        # 1. 大脑规划任务分配
        plan = await self._plan_for_multi_hand(task)

        # 2. 分发到各 Sandbox
        results: dict[str, list[str]] = {}

        for sandbox_idx, sandbox_tasks in plan.items():
            sandbox = self.sandboxes[int(sandbox_idx)]
            label = self._sandbox_labels.get(int(sandbox_idx), f"sandbox_{sandbox_idx}")

            # 执行该 Sandbox 的任务
            sandbox_results = await self._execute_sandbox_tasks(sandbox, sandbox_tasks)
            results[label] = sandbox_results

            # 更新智能体状态
            self._agents[int(sandbox_idx)].status = "completed"

        # 3. 大脑聚合结果
        aggregated = await self._aggregate_results(results)

        return {
            "task": task,
            "plan": plan,
            "execution_results": results,
            "aggregated_result": aggregated,
            "timestamp": datetime.now().isoformat(),
        }

    async def _plan_for_multi_hand(self, task: str) -> dict[str, list[dict[str, Any]]]:
        """大脑规划多环境任务分配

        Args:
            task: 任务描述

        Returns:
            各环境的任务列表
        """
        sandbox_descriptions = [
            self._sandbox_labels.get(i, f"Sandbox {i}")
            for i in range(len(self.sandboxes))
        ]

        # 构建环境描述列表
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
            response = await self.llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            plan_text = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

            # 解析 JSON
            return self._parse_plan(plan_text)

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # 默认分配：所有环境执行相同任务
            return {
                str(i): [{"tool": "code_as_policy", "args": {"code": task}}]
                for i in range(len(self.sandboxes))
            }

    def _parse_plan(self, plan_text: str) -> dict[str, list[dict[str, Any]]]:
        """解析规划文本"""
        # 尝试提取 JSON
        try:
            # 查找 JSON 块
            start = plan_text.find("{")
            end = plan_text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = plan_text[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 解析失败，使用默认分配
        logger.warning("Failed to parse plan JSON, using default")
        return {
            str(i): [{"tool": "code_as_policy", "args": {"code": "execute task"}}]
            for i in range(len(self.sandboxes))
        }

    async def _execute_sandbox_tasks(
        self, sandbox: Sandbox, tasks: list[dict[str, Any]]
    ) -> list[str]:
        """执行 Sandbox 任务列表

        Args:
            sandbox: 目标 Sandbox
            tasks: 任务列表

        Returns:
            执行结果列表
        """
        results: list[str] = []

        for task in tasks:
            tool_name = task.get("tool", "code_as_policy")
            tool_args = task.get("args", {})

            try:
                result = await sandbox.execute_tools(
                    [
                        {
                            "id": str(uuid.uuid4())[:8],
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args),
                            },
                        }
                    ]
                )
                if result:
                    results.append(result[0].get("content", "No content"))
                else:
                    results.append("No result returned")

            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                results.append(f"Error: {e}")

        return results

    async def _aggregate_results(self, results: dict[str, list[str]]) -> dict[str, Any]:
        """大脑聚合结果

        Args:
            results: 各环境执行结果

        Returns:
            聚合分析
        """
        prompt = f"""请分析以下多环境执行结果并给出总结:

执行结果:
{json.dumps(results, ensure_ascii=False, indent=2)}

请输出:
1. 各环境执行情况总结
2. 发现的问题和差异
3. 最终结论和建议
"""

        try:
            response = await self.llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            summary = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

            return {
                "summary": summary,
                "environments_count": len(results),
                "total_tasks": sum(len(r) for r in results.values()),
            }

        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            return {
                "summary": f"Aggregation failed: {e}",
                "environments_count": len(results),
            }

    async def cross_environment_test(self, test_code: str) -> dict[str, Any]:
        """跨环境测试

        Args:
            test_code: 测试代码或描述

        Returns:
            跨环境测试结果
        """
        # 规划测试方案
        test_plan = {
            "0": [
                {
                    "tool": "code_as_policy",
                    "args": {"code": test_code, "language": "python"},
                }
            ],
            "1": [
                {
                    "tool": "code_as_policy",
                    "args": {"code": test_code, "language": "javascript"},
                }
            ],
        }

        # 执行测试
        results = {}
        for sandbox_idx, tasks in test_plan.items():
            if int(sandbox_idx) < len(self.sandboxes):
                sandbox = self.sandboxes[int(sandbox_idx)]
                label = self._sandbox_labels.get(
                    int(sandbox_idx), f"sandbox_{sandbox_idx}"
                )
                results[label] = await self._execute_sandbox_tasks(sandbox, tasks)

        # 检查跨环境一致性
        python_result = results.get("python_env", [""])
        node_result = results.get("node_env", [""])

        cross_env_valid = "PASS" in str(python_result) and "PASS" in str(node_result)

        return {
            "test_code": test_code[:200],
            "python_test": python_result,
            "node_test": node_result,
            "cross_env_valid": cross_env_valid,
            "timestamp": datetime.now().isoformat(),
        }

    def get_sandboxes_status(self) -> list[dict[str, Any]]:
        """获取所有 Sandbox 状态"""
        return [
            {
                "index": i,
                "label": self._sandbox_labels.get(i, f"sandbox_{i}"),
                "status": self._agents[i].status,
                "sandbox_state": sandbox.get_status(),
            }
            for i, sandbox in enumerate(self.sandboxes)
        ]


class MultiBrainMultiHandOrchestrator:
    """多脑多手编排器：多个 Claude + 多个 Sandbox + Session 协调

    适用场景：最复杂的多步骤任务

    核心特性：
    - Session 协调：共享 Session 作为协调中心
    - 独立组合：每个 Claude 有自己的 Sandbox
    - 动态分配：根据进度调整任务分配
    - 消息总线：智能体间通信
    """

    def __init__(
        self,
        session: SessionEventStream,
        agent_sandbox_pairs: list[tuple[LLMClient, Sandbox]] | None = None,
        message_bus: "InterAgentMessageBus | None" = None,
    ):
        """初始化多脑多手编排器

        Args:
            session: 共享协调中心
            agent_sandbox_pairs: Claude + Sandbox 组合列表
            message_bus: 消息总线（可选）
        """
        self.session = session
        self._pairs: list[tuple[LLMClient, Sandbox]] = agent_sandbox_pairs or []
        self._message_bus = message_bus

        # 创建智能体实例
        self._agents: list[AgentInstance] = []
        self._pair_ids: list[str] = []

        for _, (llm_client, sandbox) in enumerate(self._pairs):
            pair_id = str(uuid.uuid4())[:8]
            self._pair_ids.append(pair_id)
            self._agents.append(
                AgentInstance(
                    id=pair_id,
                    llm_client=llm_client,
                    sandbox=sandbox,
                )
            )

        self._task_assignments: dict[str, list[dict]] = {}

        logger.info(
            f"MultiBrainMultiHandOrchestrator initialized: "
            f"pairs={len(self._pairs)}, session={session.session_id}"
        )

    def register_pair(
        self, llm_client: LLMClient, sandbox: Sandbox, pair_id: str | None = None
    ) -> str:
        """注册 Claude + Sandbox 组合

        Args:
            llm_client: LLM 客户端
            sandbox: 执行沙盒
            pair_id: 组合 ID（可选）

        Returns:
            组合 ID
        """
        pair_id = pair_id or str(uuid.uuid4())[:8]
        self._pairs.append((llm_client, sandbox))
        self._pair_ids.append(pair_id)
        self._agents.append(
            AgentInstance(
                id=pair_id,
                llm_client=llm_client,
                sandbox=sandbox,
            )
        )

        logger.info(f"Pair registered: {pair_id}")
        return pair_id

    async def coordinated_execution(self, task: str) -> CoordinationResult:
        """协调执行

        流程:
        1. Session 记录任务
        2. 各组合独立执行
        3. 结果记录到 Session
        4. Session 协调合并

        Args:
            task: 任务描述

        Returns:
            协调结果
        """
        # 1. Session 记录任务
        self.session.emit_event(
            EventType.SESSION_START,
            {
                "task": task,
                "pairs": self._pair_ids,
                "mode": "multi_brain_multi_hand",
            },
        )

        # 2. 各组合独立执行（并行）
        pair_results = await asyncio.gather(
            *[self._execute_pair(agent, task) for agent in self._agents],
            return_exceptions=True,
        )

        # 3. 结果记录到 Session
        processed_results: list[dict[str, Any]] = []
        for pair_id, result in zip(self._pair_ids, pair_results, strict=True):
            if isinstance(result, Exception):
                self.session.emit_event(
                    EventType.ERROR_OCCURRED,
                    {
                        "pair_id": pair_id,
                        "error": str(result),
                    },
                )
                processed_results.append(
                    {
                        "pair_id": pair_id,
                        "status": "failed",
                        "error": str(result),
                    }
                )
            else:
                self.session.emit_event(
                    EventType.SUBAGENT_RESULT,
                    {
                        "pair_id": pair_id,
                        "result": result,
                    },
                )
                processed_results.append(
                    {
                        "pair_id": pair_id,
                        "status": "completed",
                        "result": result,
                    }
                )

        # 4. Session 协调合并
        merged = await self._merge_from_session()

        # 5. 记录会话结束
        self.session.emit_event(
            EventType.SESSION_END,
            {
                "reason": "completed",
                "pairs_count": len(self._pair_ids),
            },
        )

        return CoordinationResult(
            task=task,
            agent_results=processed_results,
            merged_result=merged,
            session_events=self.session.get_events(),
        )

    async def _execute_pair(
        self,
        agent: AgentInstance,
        task: str,
    ) -> dict[str, Any]:
        """单个组合执行

        Args:
            agent: 智能体实例
            task: 任务描述

        Returns:
            执行结果
        """
        agent.status = "running"

        # 1. 从 Session 获取当前状态
        session_state = self.session.get_current_state()

        # 2. 构建上下文（包含其他组合的进度）
        context = self._build_pair_context(task, session_state)

        # 3. Claude 推理
        try:
            response = await agent.llm_client.reason(context)

            # 4. Sandbox 执行工具
            tool_results: list[str] = []
            tool_calls = (
                response.get("choices", [{}])[0].get("message", {}).get("tool_calls")
            )

            if tool_calls and agent.sandbox:
                results = await agent.sandbox.execute_tools(tool_calls)
                tool_results = [r.get("content", "") for r in results]

            agent.status = "completed"

            return {
                "pair_id": agent.id,
                "response": response,
                "tool_results": tool_results,
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"Pair {agent.id} execution failed: {e}")
            agent.status = "failed"
            return {
                "pair_id": agent.id,
                "error": str(e),
                "status": "failed",
            }

    def _build_pair_context(
        self, task: str, session_state: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """构建组合上下文

        Args:
            task: 任务描述
            session_state: Session 状态

        Returns:
            上下文消息列表
        """
        # 包含任务和其他组合的进度
        other_pairs_progress = [
            {"pair_id": agent.id, "status": agent.status}
            for agent in self._agents
            if agent.id != session_state.get("current_pair_id")
        ]

        return [
            {
                "role": "system",
                "content": "你是一个协作智能体，正在与其他智能体协同完成任务。",
            },
            {
                "role": "user",
                "content": f"""任务: {task}

其他智能体状态:
{json.dumps(other_pairs_progress, ensure_ascii=False, indent=2)}

请执行你的部分任务，并输出结果或下一步建议。
""",
            },
        ]

    async def _merge_from_session(self) -> dict[str, Any]:
        """从 Session 合并所有结果"""
        # 获取所有 subagent_result 事件
        pair_events = [
            e
            for e in self.session.get_events()
            if e["type"] == EventType.SUBAGENT_RESULT.value
        ]

        # 合并逻辑
        successful_pairs = [e for e in pair_events if "error" not in e["data"]]
        failed_pairs = [e for e in pair_events if "error" in e["data"]]

        # 收集结果
        all_results = []
        for event in successful_pairs:
            result_data = event["data"].get("result", {})
            if isinstance(result_data, dict):
                all_results.append(result_data)

        # 生成合并摘要
        merged_summary = await self._generate_merge_summary(all_results)

        return {
            "total_pairs": len(pair_events),
            "successful_pairs": len(successful_pairs),
            "failed_pairs": len(failed_pairs),
            "results": all_results,
            "merged_summary": merged_summary,
        }

    async def _generate_merge_summary(self, results: list[dict[str, Any]]) -> str:
        """生成合并摘要"""
        if not results:
            return "No results to merge"

        if not self._agents:
            return f"Collected {len(results)} results"

        # 使用第一个大脑生成摘要
        prompt = f"""请总结以下多个智能体的执行结果:

{json.dumps(results[:5], ensure_ascii=False, indent=2)}

请输出:
1. 各智能体贡献总结
2. 整体完成情况
3. 遗留问题或下一步建议
"""

        try:
            response = await self._agents[0].llm_client.reason(
                [{"role": "user", "content": prompt}]
            )
            return (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

        except Exception as e:
            logger.error(f"Merge summary failed: {e}")
            return f"Generated {len(results)} results"

    async def dynamic_task_assignment(self, task: str) -> dict[str, Any]:
        """动态任务分配

        根据执行进度动态调整任务分配

        Args:
            task: 任务描述

        Returns:
            分配结果
        """
        # 1. 初始分配
        initial_assignments = await self._initial_assignment(task)

        # 2. 执行监控
        final_results: list[dict[str, Any]] = []
        iteration = 0

        while iteration < MAX_DYNAMIC_ITERATIONS:
            iteration += 1

            # 执行当前分配
            results = await self._execute_assignments(initial_assignments)
            final_results = results

            # 检查完成状态
            completed_pairs = [
                r["pair_id"] for r in results if r.get("status") == "completed"
            ]

            if len(completed_pairs) == len(self._pair_ids):
                break

            # 3. 动态重分配
            remaining_pairs = [
                pid for pid in self._pair_ids if pid not in completed_pairs
            ]

            if remaining_pairs:
                initial_assignments = await self._reassign_tasks(
                    task, completed_pairs, remaining_pairs
                )

        return {
            "task": task,
            "initial_assignments": initial_assignments,
            "final_results": final_results,
            "iterations": iteration,
            "completed": len(
                [r for r in final_results if r.get("status") == "completed"]
            ),
        }

    async def _initial_assignment(self, task: str) -> dict[str, list[dict]]:
        """初始任务分配"""
        # 简化：将任务平均分配给各组合
        assignments: dict[str, list[dict]] = {}

        for pair_id in self._pair_ids:
            assignments[pair_id] = [{"task": task, "phase": "initial"}]

        return assignments

    async def _execute_assignments(
        self, assignments: dict[str, list[dict]]
    ) -> list[dict[str, Any]]:
        """执行分配的任务"""
        results = []

        for pair_id, tasks in assignments.items():
            # 找到对应的智能体
            agent = next((a for a in self._agents if a.id == pair_id), None)
            if not agent:
                results.append(
                    {
                        "pair_id": pair_id,
                        "status": "failed",
                        "error": "Agent not found",
                    }
                )
                continue

            # 执行任务
            for task_item in tasks:
                result = await self._execute_pair(agent, task_item.get("task", ""))
                results.append(result)

        return results

    async def _reassign_tasks(
        self,
        remaining_task: str,
        completed_pairs: list[str],
        remaining_pairs: list[str],
    ) -> dict[str, list[dict]]:
        """重新分配任务

        Args:
            remaining_task: 剩余任务
            completed_pairs: 已完成的组合
            remaining_pairs: 待完成的组合

        Returns:
            新的分配方案
        """
        # 获取已完成的结果作为上下文
        completed_results = [
            e["data"].get("result")
            for e in self.session.get_events()
            if e["type"] == EventType.SUBAGENT_RESULT.value
            and e["data"].get("pair_id") in completed_pairs
        ]

        # 新分配
        assignments: dict[str, list[dict]] = {}
        for pair_id in remaining_pairs:
            assignments[pair_id] = [
                {
                    "task": remaining_task,
                    "context": completed_results,
                    "phase": "reassigned",
                }
            ]

        return assignments

    def get_pairs_status(self) -> list[dict[str, Any]]:
        """获取所有组合状态"""
        return [
            {
                "pair_id": agent.id,
                "status": agent.status,
            }
            for agent in self._agents
        ]


class InterAgentMessageBus:
    """智能体间消息传递总线

    基于 SessionEventStream 实现的消息传递机制：
    - 发送消息：记录到 Session
    - 接收消息：从 Session 筛选
    - 广播消息：批量发送

    核心特性：
    - 异步消息传递
    - 类型订阅机制
    - 广播支持
    """

    def __init__(self, session: SessionEventStream):
        """初始化消息总线

        Args:
            session: Session 事件流
        """
        self.session = session
        self._message_handlers: dict[str, list[Callable]] = {}
        self._pair_ids: list[str] = []

        logger.info(f"InterAgentMessageBus initialized: session={session.session_id}")

    def set_pair_ids(self, pair_ids: list[str]) -> None:
        """设置智能体 ID 列表（用于广播）"""
        self._pair_ids = pair_ids

    def register_handler(
        self, message_type: str, handler: Callable[[dict[str, Any]], Any]
    ) -> None:
        """注册消息处理器

        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)
        logger.debug(f"Handler registered: type={message_type}")

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: dict[str, Any],
    ) -> int:
        """发送消息

        Args:
            from_agent: 发送方 ID
            to_agent: 接收方 ID
            message_type: 消息类型
            content: 消息内容

        Returns:
            事件 ID
        """
        message_id = self.session.emit_event(
            "inter_agent_message",
            {
                "from": from_agent,
                "to": to_agent,
                "type": message_type,
                "content": content,
                "timestamp": time.time(),
            },
        )

        logger.debug(f"Message sent: {from_agent} -> {to_agent}, type={message_type}")
        return message_id

    async def receive_messages(
        self, agent_id: str, message_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """接收消息

        Args:
            agent_id: 接收方 ID
            message_types: 过滤的消息类型（可选）

        Returns:
            消息列表
        """
        # 从 Session 筛选消息
        messages = [
            e["data"]
            for e in self.session.get_events()
            if e["type"] == "inter_agent_message" and e["data"].get("to") == agent_id
        ]

        # 类型过滤
        if message_types:
            messages = [m for m in messages if m.get("type") in message_types]

        # 处理消息
        for msg in messages:
            handlers = self._message_handlers.get(msg.get("type", ""), [])
            for handler in handlers:
                try:
                    # 支持同步和异步处理器
                    if asyncio.iscoroutinefunction(handler):
                        await handler(msg)
                    else:
                        handler(msg)
                except Exception as e:
                    logger.warning(f"Handler error: {e}")

        return messages

    async def broadcast(
        self,
        from_agent: str,
        message_type: str,
        content: dict[str, Any],
        exclude_self: bool = True,
    ) -> list[int]:
        """广播消息

        Args:
            from_agent: 发送方 ID
            message_type: 消息类型
            content: 消息内容
            exclude_self: 是否排除自己

        Returns:
            事件 ID 列表
        """
        message_ids: list[int] = []
        targets = [
            pid for pid in self._pair_ids if not (exclude_self and pid == from_agent)
        ]

        for target in targets:
            message_id = await self.send_message(
                from_agent, target, message_type, content
            )
            message_ids.append(message_id)

        logger.debug(f"Broadcast: {from_agent} -> {len(targets)} targets")
        return message_ids

    def get_message_count(self) -> int:
        """获取消息总数"""
        return len(
            [e for e in self.session.get_events() if e["type"] == "inter_agent_message"]
        )

    def clear_handlers(self) -> None:
        """清除所有处理器"""
        self._message_handlers.clear()
        logger.debug("All handlers cleared")


# === 工具注册 ===


def register_collaboration_tools(registry: Any) -> None:
    """注册协作工具到 Registry

    Args:
        registry: 工具注册表
    """
    # 导入并注册协作工具
    from src.tools.collaboration_tools import register_tools

    register_tools(registry)
