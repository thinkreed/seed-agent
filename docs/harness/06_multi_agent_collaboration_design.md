# 优化点 06: 多智能体协作模式

> **版本**: v1.0  
> **创建日期**: 2026-05-03  
> **优先级**: 低  
> **依赖**: 02_harness_sandbox_decoupling_design  
> **参考来源**: Harness Engineering "多智能体协作模式"

---

## 问题分析

### Harness Engineering 多智能体协作模式

得益于三件套解耦，自然支持多种协作模式：

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| **多脑一手** | 多个 Claude 实例共享一个 Sandbox | 多角度分析同一份代码 (安全审查 + 性能优化) |
| **一脑多手** | 一个 Claude 控制多个 Sandbox | 在不同环境执行任务 (Python + Node.js) |
| **多脑多手** | 多个 Claude 各有 Sandbox，通过共享 Session 协调 | 最复杂的多步骤任务 |

**关键架构**:

```
多脑一手模式:
┌───────────┐  ┌───────────┐
│ Claude 1  │  │ Claude 2  │  ← 多个大脑
│ (安全审查) │  │ (性能优化) │
└─────┬─────┘  └─────┬─────┘
      │              │
      └──────┬───────┘
             │
             ▼
    ┌─────────────────┐
    │   Shared Sandbox │  ← 共享工作台
    └─────────────────┘

一脑多手模式:
┌─────────────────┐
│    Claude       │  ← 单个大脑
│   (主控制器)     │
└─────┬─────┬─────┘
      │     │
      ▼     ▼
┌─────────┐  ┌─────────┐
│ Sandbox │  │ Sandbox │  ← 多个工作台
│ (Python)│  │ (Node.js)│
└─────────┘  └─────────┘

多脑多手模式:
┌───────────┐        ┌───────────┐
│ Claude 1  │        │ Claude 2  │
└─────┬─────┘        └─────┬─────┘
      │                    │
      ▼                    ▼
┌───────────┐        ┌───────────┐
│ Sandbox 1 │        │ Sandbox 2 │
└─────┬─────┘        └─────┬─────┘
      │                    │
      └──────┬─────────────┘
             │
             ▼
    ┌─────────────────┐
    │  Shared Session │  ← 共享协调中心
    └─────────────────┘
```

### seed-agent 当前 Subagent 机制

**已实现**:

| 能力 | 实现位置 | 描述 |
|------|----------|------|
| SubagentInstance | `subagent.py` | 独立上下文子代理 |
| SubagentManager | `subagent_manager.py` | 并行执行调度 (最大 3 个) |
| RalphSubagentOrchestrator | `subagent_manager.py` | Plan→Implement→Review 流程 |

**当前模式**:

```python
# 一脑多手 (部分支持)
class SubagentManager:
    async def run_parallel(self, task_ids: list[str]) -> dict[str, SubagentResult]:
        """并行执行多个子代理"""
        tasks = [self.run_subagent(task_id) for task_id in task_ids]
        results = await asyncio.gather(*tasks)
        return results
```

**问题**:
- ❌ 无共享 Sandbox 模式 (多脑一手)
- ❌ 无共享 Session 协调 (多脑多手)
- ❌ Subagent 间无通信机制
- ❌ 无动态任务分配
- ❌ 无协作进度同步

---

## 设计方案

### 1. 多脑一手模式

```python
class MultiBrainOneHandOrchestrator:
    """多脑一手: 多个 Claude 共享一个 Sandbox"""
    
    def __init__(
        self,
        sandbox: Sandbox,
        num_brains: int = 2,
        claude_configs: list[dict] = None,
    ):
        self.sandbox = sandbox  # 共享工作台
        
        # 创建多个 Claude 大脑
        if claude_configs:
            self.brains = [
                ClaudeClient(LLMGateway(cfg["gateway"]), cfg["model_id"])
                for cfg in claude_configs
            ]
        else:
            self.brains = [
                ClaudeClient(LLMGateway(DEFAULT_GATEWAY), DEFAULT_MODEL)
                for _ in range(num_brains)
            ]
        
        self._perspectives: list[str] = []  # 分析视角
    
    def register_perspective(self, brain_index: int, perspective: str) -> None:
        """为 Claude 注册分析视角
        
        Args:
            brain_index: 大脑索引
            perspective: 分析视角 (如 "security", "performance", "readability")
        """
        self._perspectives.append(perspective)
    
    async def analyze_from_multiple_angles(self, target: str) -> dict:
        """多角度分析
        
        Args:
            target: 分析目标 (文件路径、代码片段等)
        
        Returns:
            多角度分析结果
        """
        # 1. 共享 Sandbox 读取目标
        target_content = await self.sandbox.execute_tool({
            "function": {"name": "file_read", "arguments": json.dumps({"path": target})}
        })
        
        # 2. 每个 Claude 从不同视角分析
        analyses = await asyncio.gather(
            *[self._analyze_with_perspective(brain, perspective, target_content)
              for brain, perspective in zip(self.brains, self._perspectives)]
        )
        
        # 3. 结果聚合
        return {
            "target": target,
            "analyses": [
                {"perspective": perspective, "result": analysis}
                for perspective, analysis in zip(self._perspectives, analyses)
            ],
            "sandbox_state": self.sandbox.get_state(),
        }
    
    async def _analyze_with_perspective(
        self,
        brain: ClaudeClient,
        perspective: str,
        content: str,
    ) -> str:
        """从特定视角分析"""
        prompt = f"""请从 {perspective} 视角分析以下代码:

```
{content}
```

分析要点:
1. {perspective} 相关问题
2. 潜在风险
3. 改进建议
"""
        
        response = await brain.reason([{"role": "user", "content": prompt}])
        return response["choices"][0]["message"]["content"]
    
    async def collaborative_improve(self, target: str) -> str:
        """协作改进
        
        流程:
        1. 多角度分析
        2. 融合改进建议
        3. 共享 Sandbox 执行改进
        """
        # 1. 多角度分析
        analysis_result = await self.analyze_from_multiple_angles(target)
        
        # 2. 融合改进建议 (由主 Claude 决断)
        merged_suggestions = await self._merge_suggestions(analysis_result)
        
        # 3. 共享 Sandbox 执行改进
        improvement_result = await self.sandbox.execute_tool({
            "function": {"name": "file_edit", "arguments": json.dumps({
                "path": target,
                "old_str": merged_suggestions["old"],
                "new_str": merged_suggestions["new"],
            })}
        })
        
        return improvement_result
```

### 2. 一脑多手模式

```python
class OneBrainMultiHandOrchestrator:
    """一脑多手: 一个 Claude 控制多个 Sandbox"""
    
    def __init__(
        self,
        brain: ClaudeClient,
        sandbox_configs: list[dict],
    ):
        self.brain = brain  # 单个大脑
        
        # 创建多个工作台
        self.sandboxes: list[Sandbox] = [
            Sandbox(**config) for config in sandbox_configs
        ]
        
        self._sandbox_labels: dict[int, str] = {}  # 工作台标签
    
    def label_sandbox(self, index: int, label: str) -> None:
        """为 Sandbox 标签
        
        Args:
            index: Sandbox 索引
            label: 标签 (如 "python_env", "node_env", "browser")
        """
        self._sandbox_labels[index] = label
    
    async def execute_in_multiple_environments(self, task: str) -> dict:
        """在不同环境执行任务
        
        Args:
            task: 任务描述
        
        Returns:
            各环境执行结果
        """
        # 1. 大脑规划 (决定各环境任务)
        plan = await self._plan_for_multi_hand(task)
        
        # 2. 分发到各 Sandbox
        results = {}
        
        for sandbox_idx, sandbox_tasks in plan.items():
            sandbox = self.sandboxes[sandbox_idx]
            label = self._sandbox_labels.get(sandbox_idx, f"sandbox_{sandbox_idx}")
            
            # 执行该 Sandbox 的任务
            sandbox_results = await self._execute_sandbox_tasks(sandbox, sandbox_tasks)
            results[label] = sandbox_results
        
        # 3. 大脑聚合结果
        aggregated = await self._aggregate_results(results)
        
        return {
            "plan": plan,
            "execution_results": results,
            "aggregated_result": aggregated,
        }
    
    async def _plan_for_multi_hand(self, task: str) -> dict[int, list[dict]]:
        """大脑规划多环境任务分配"""
        sandbox_descriptions = [
            self._sandbox_labels.get(i, f"Sandbox {i}: {self.sandboxes[i].isolation_level}")
            for i in range(len(self.sandboxes))
        ]
        
        prompt = f"""请为以下任务规划多环境执行方案:

任务: {task}

可用环境:
{chr(10).join(sandbox_descriptions)}

规划格式:
环境 0: [任务列表]
环境 1: [任务列表]
...
"""
        
        response = await self.brain.reason([{"role": "user", "content": prompt}])
        plan_text = response["choices"][0]["message"]["content"]
        
        # 解析规划
        return self._parse_plan(plan_text)
    
    async def _execute_sandbox_tasks(self, sandbox: Sandbox, tasks: list[dict]) -> list[str]:
        """执行 Sandbox 任务列表"""
        results = []
        
        for task in tasks:
            result = await sandbox.execute_tool({
                "function": {
                    "name": task["tool"],
                    "arguments": json.dumps(task["args"])
                }
            })
            results.append(result)
        
        return results
    
    async def cross_environment_test(self, code_path: str) -> dict:
        """跨环境测试
        
        在 Python 和 Node.js 环境同时测试代码
        """
        # 1. 规划测试方案
        test_plan = await self._plan_cross_env_test(code_path)
        
        # 2. Python Sandbox 执行 Python 测试
        python_results = await self.sandboxes[0].execute_tool({
            "function": {
                "name": "code_as_policy",
                "arguments": json.dumps({
                    "code": test_plan["python_test"],
                    "language": "python"
                })
            }
        })
        
        # 3. Node.js Sandbox 执行 JS 测试
        node_results = await self.sandboxes[1].execute_tool({
            "function": {
                "name": "code_as_policy",
                "arguments": json.dumps({
                    "code": test_plan["node_test"],
                    "language": "javascript"
                })
            }
        })
        
        return {
            "python_test": python_results,
            "node_test": node_results,
            "cross_env_valid": "PASS" in python_results and "PASS" in node_results,
        }
```

### 3. 多脑多手模式 + Session 共享协调

```python
class MultiBrainMultiHandOrchestrator:
    """多脑多手: 多个 Claude + 多个 Sandbox + Session 协调"""
    
    def __init__(
        self,
        brain_sandbox_pairs: list[tuple[ClaudeClient, Sandbox]],
        shared_session: SessionEventStream,
    ):
        self._pairs = brain_sandbox_pairs
        self.shared_session = shared_session  # 共享协调中心
        
        self._pair_ids: list[str] = []
        self._task_assignments: dict[str, list[dict]] = {}
    
    def register_pair(self, brain: ClaudeClient, sandbox: Sandbox, pair_id: str = None) -> str:
        """注册 Claude + Sandbox 组合"""
        pair_id = pair_id or str(uuid.uuid4())[:8]
        self._pairs.append((brain, sandbox))
        self._pair_ids.append(pair_id)
        return pair_id
    
    async def coordinated_execution(self, task: str) -> dict:
        """协调执行
        
        流程:
        1. Session 记录任务
        2. 各组合独立执行
        3. 结果记录到 Session
        4. Session 协调合并
        """
        # 1. Session 记录任务
        self.shared_session.emit_event("multi_agent_task", {
            "task": task,
            "pairs": self._pair_ids,
        })
        
        # 2. 各组合独立执行
        pair_results = await asyncio.gather(
            *[self._execute_pair(brain, sandbox, task, pair_id)
              for brain, sandbox, pair_id in zip(
                  [p[0] for p in self._pairs],
                  [p[1] for p in self._pairs],
                  self._pair_ids
              )]
        )
        
        # 3. 结果记录到 Session
        for pair_id, result in zip(self._pair_ids, pair_results):
            self.shared_session.emit_event("pair_result", {
                "pair_id": pair_id,
                "result": result,
            })
        
        # 4. Session 协调合并
        merged = await self._merge_from_session()
        
        return {
            "task": task,
            "pair_results": pair_results,
            "merged_result": merged,
            "session_events": self.shared_session.get_events(),
        }
    
    async def _execute_pair(
        self,
        brain: ClaudeClient,
        sandbox: Sandbox,
        task: str,
        pair_id: str,
    ) -> dict:
        """单个组合执行"""
        # 1. 从 Session 获取当前状态
        session_state = self.shared_session.replay_to_state(
            self.shared_session._event_counter
        )
        
        # 2. 构建上下文 (包含其他组合的进度)
        context = self._build_pair_context(task, session_state)
        
        # 3. Claude 推理
        response = await brain.reason(context)
        
        # 4. Sandbox 执行工具
        results = []
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                result = await sandbox.execute_tool(tc)
                results.append(result)
        
        return {
            "pair_id": pair_id,
            "response": response,
            "tool_results": results,
        }
    
    async def _merge_from_session(self) -> dict:
        """从 Session 合并所有结果"""
        # 获取所有 pair_result 事件
        pair_events = [
            e for e in self.shared_session.get_events()
            if e["type"] == "pair_result"
        ]
        
        # 合并逻辑
        merged = {
            "total_pairs": len(pair_events),
            "successful_pairs": sum(1 for e in pair_events if "error" not in e["data"]["result"]),
            "results": [e["data"]["result"] for e in pair_events],
        }
        
        return merged
    
    # === 动态任务分配 ===
    
    async def dynamic_task_assignment(self, task: str) -> dict:
        """动态任务分配
        
        根据执行进度动态调整任务分配
        """
        # 1. 初始分配
        initial_assignments = await self._initial_assignment(task)
        
        # 2. 执行监控
        for iteration in range(MAX_DYNAMIC_ITERATIONS):
            # 执行当前分配
            results = await self._execute_assignments(initial_assignments)
            
            # 检查完成状态
            completed_pairs = self._check_completion(results)
            
            if len(completed_pairs) == len(self._pairs):
                break
            
            # 3. 动态重分配
            remaining_task = self._extract_remaining_task(results)
            new_assignments = await self._reassign_tasks(remaining_task, completed_pairs)
            
            initial_assignments = new_assignments
        
        return {
            "initial_assignments": initial_assignments,
            "final_results": results,
            "iterations": iteration,
        }
    
    async def _reassign_tasks(
        self,
        remaining_task: str,
        completed_pairs: list[str],
    ) -> dict[str, list[dict]]:
        """重新分配任务给未完成的组合"""
        active_pairs = [pid for pid in self._pair_ids if pid not in completed_pairs]
        
        # 使用 Session 中已完成的结果辅助决策
        completed_results = [
            e["data"]["result"]
            for e in self.shared_session.get_events()
            if e["type"] == "pair_result" and e["data"]["pair_id"] in completed_pairs
        ]
        
        # 新分配
        assignments = {}
        for pair_id in active_pairs:
            assignments[pair_id] = [{"task": remaining_task, "context": completed_results}]
        
        return assignments
```

### 4. 协作通信机制

```python
class InterAgentMessageBus:
    """智能体间消息传递总线"""
    
    def __init__(self, session: SessionEventStream):
        self.session = session
        self._message_handlers: dict[str, list[Callable]] = {}
    
    def register_handler(self, message_type: str, handler: Callable) -> None:
        """注册消息处理器"""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)
    
    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: dict,
    ) -> int:
        """发送消息
        
        Args:
            from_agent: 发送方 ID
            to_agent: 接收方 ID
            message_type: 消息类型
            content: 消息内容
        
        Returns:
            message_id
        """
        message_id = self.session.emit_event("inter_agent_message", {
            "from": from_agent,
            "to": to_agent,
            "type": message_type,
            "content": content,
            "timestamp": time.time(),
        })
        
        return message_id
    
    async def receive_messages(self, agent_id: str) -> list[dict]:
        """接收消息
        
        Args:
            agent_id: 接收方 ID
        
        Returns:
            消息列表
        """
        # 从 Session 筛选消息
        messages = [
            e["data"]
            for e in self.session.get_events()
            if e["type"] == "inter_agent_message" and e["data"]["to"] == agent_id
        ]
        
        # 处理消息
        for msg in messages:
            handlers = self._message_handlers.get(msg["type"], [])
            for handler in handlers:
                await handler(msg)
        
        return messages
    
    async def broadcast(self, from_agent: str, message_type: str, content: dict) -> None:
        """广播消息"""
        for pair_id in self._pair_ids:
            await self.send_message(from_agent, pair_id, message_type, content)
```

---

## 实施步骤

### Phase 1: 多脑一手模式 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 实现 MultiBrainOneHandOrchestrator | 共享 Sandbox 正确 |
| 1.2 | 实现多角度分析 | analyze_from_multiple_angles |
| 1.3 | 实现协作改进 | collaborative_improve |

### Phase 2: 一脑多手模式 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 实现 OneBrainMultiHandOrchestrator | 多 Sandbox 正确 |
| 2.2 | 实现任务分配 | plan_for_multi_hand |
| 2.3 | 实现跨环境测试 | cross_environment_test |

### Phase 3: 多脑多手 + Session 协调 (5天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | 实现 MultiBrainMultiHandOrchestrator | Session 协调正确 |
| 3.2 | 实现消息总线 | InterAgentMessageBus |
| 3.3 | 实现动态任务分配 | dynamic_task_assignment |
| 3.4 | 集成测试 | 三种模式协作正确 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **多角度分析能力** | 多脑一手模式，安全+性能+可读性同时分析 |
| **跨环境执行能力** | 一脑多手模式，Python+Node.js 同时测试 |
| **复杂任务协作** | 多脑多手模式，Session 协调分布式任务 |
| **动态任务分配** | 根据进度自动调整分配 |
| **智能体间通信** | 消息总线支持协作同步 |

---

## 测试计划

```python
def test_multi_brain_one_hand():
    sandbox = Sandbox(isolation_level="process")
    orchestrator = MultiBrainOneHandOrchestrator(sandbox, num_brains=2)
    
    orchestrator.register_perspective(0, "security")
    orchestrator.register_perspective(1, "performance")
    
    # 多角度分析
    result = await orchestrator.analyze_from_multiple_angles("src/agent_loop.py")
    
    assert len(result["analyses"]) == 2
    assert result["analyses"][0]["perspective"] == "security"

def test_one_brain_multi_hand():
    brain = ClaudeClient(LLMGateway(config), model_id)
    orchestrator = OneBrainMultiHandOrchestrator(brain, [
        {"isolation_level": "process", "label": "python"},
        {"isolation_level": "process", "label": "node"},
    ])
    
    # 跨环境执行
    result = await orchestrator.execute_in_multiple_environments("测试 API 兼容性")
    
    assert "python" in result["execution_results"]
    assert "node" in result["execution_results"]

def test_multi_brain_multi_hand():
    session = SessionEventStream("test", Path("/tmp/test"))
    orchestrator = MultiBrainMultiHandOrchestrator([], session)
    
    orchestrator.register_pair(claude1, sandbox1, "pair_1")
    orchestrator.register_pair(claude2, sandbox2, "pair_2")
    
    # 协调执行
    result = await orchestrator.coordinated_execution("实现用户认证")
    
    assert len(result["pair_results"]) == 2
    assert result["merged_result"]["total_pairs"] == 2
```

---

## 相关文档

- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Sandbox 隔离
- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 协调中心