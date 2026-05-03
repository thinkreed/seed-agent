# 优化点 06: 多智能体协作模式

> **版本**: v2.0 (已落地实现)
> **创建日期**: 2026-05-03
> **实现日期**: 2026-05-03
> **优先级**: 低
> **依赖**: 02_harness_sandbox_decoupling_design
> **状态**: ✅ 已完成
> **参考来源**: Harness Engineering "多智能体协作模式"

---

## 实现状态

### ✅ 已完成模块

| 模块 | 文件 | 实现状态 |
|------|------|----------|
| **MultiBrainOneHandOrchestrator** | `src/collaboration.py` | ✅ 已实现 |
| **OneBrainMultiHandOrchestrator** | `src/collaboration.py` | ✅ 已实现 |
| **MultiBrainMultiHandOrchestrator** | `src/collaboration.py` | ✅ 已实现 |
| **InterAgentMessageBus** | `src/collaboration.py` | ✅ 已实现 |
| **协作工具集** | `src/tools/collaboration_tools.py` | ✅ 已实现 |
| **测试** | `tests/test_collaboration.py` | ✅ 已更新 |

### 关键变更

1. **重写设计**: 不兼容旧 Subagent 设计，全新协作架构
2. **三种模式完整实现**: 多脑一手、一脑多手、多脑多手
3. **Session 协调**: 使用 SessionEventStream 作为协调中心
4. **消息总线**: InterAgentMessageBus 支持智能体间通信

---

## 落地架构

### 多脑一手模式

```
┌───────────┐  ┌───────────┐
│ LLMClient │  │ LLMClient │  ← 多个大脑
│(安全审查) │  │(性能优化) │
└─────┬─────┘  └─────┬─────┘
      │              │
      └──────┬───────┘
             │
             ▼
    ┌─────────────────┐
    │   Shared Sandbox │  ← 共享工作台
    └─────────────────┘
```

**实现**:
- `MultiBrainOneHandOrchestrator` 管理多个 LLMClient + 一个共享 Sandbox
- `analyze_from_multiple_angles()` 多角度分析
- `collaborative_improve()` 融合建议并执行改进

### 一脑多手模式

```
┌─────────────────┐
│    LLMClient    │  ← 单个大脑
│   (主控制器)     │
└─────┬─────┬─────┘
      │     │
      ▼     ▼
┌─────────┐  ┌─────────┐
│ Sandbox │  │ Sandbox │  ← 多个工作台
│ (Python)│  │ (Node.js)│
└─────────┘  └─────────┘
```

**实现**:
- `OneBrainMultiHandOrchestrator` 管理一个 LLMClient + 多个 Sandbox
- `execute_in_multiple_environments()` 跨环境执行
- `cross_environment_test()` 跨环境测试

### 多脑多手模式 + Session 协调

```
┌───────────┐        ┌───────────┐
│ LLMClient │        │ LLMClient │
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
    │ SessionEventStream │  ← 共享协调中心
    │ + MessageBus     │
    └─────────────────┘
```

**实现**:
- `MultiBrainMultiHandOrchestrator` 管理多个 (LLMClient, Sandbox) 组合
- `coordinated_execution()` Session 协调执行
- `dynamic_task_assignment()` 动态任务分配
- `InterAgentMessageBus` 智能体间消息传递

---

## 实现细节

### MultiBrainOneHandOrchestrator

```python
class MultiBrainOneHandOrchestrator:
    """多脑一手: 多个 Claude 共享一个 Sandbox"""

    def __init__(
        self,
        sandbox: Sandbox,
        llm_clients: list[LLMClient],
        perspectives: list[str] | None = None,
    ):
        self.sandbox = sandbox  # 共享工作台
        self.llm_clients = llm_clients  # 多个大脑
        self._perspectives = perspectives or ["perspective_0", ...]

    async def analyze_from_multiple_angles(self, target: str) -> dict:
        """多角度分析

        1. 共享 Sandbox 读取目标
        2. 每个 Claude 从不同视角分析（并行）
        3. 返回多角度分析结果
        """

    async def collaborative_improve(self, target: str) -> dict:
        """协作改进

        1. 多角度分析
        2. 融合改进建议（由主 Claude 决断）
        3. 共享 Sandbox 执行改进
        """
```

### OneBrainMultiHandOrchestrator

```python
class OneBrainMultiHandOrchestrator:
    """一脑多手: 一个 Claude 控制多个 Sandbox"""

    def __init__(
        self,
        llm_client: LLMClient,
        sandbox_configs: list[dict],
        labels: list[str] | None = None,
    ):
        self.llm_client = llm_client  # 单个大脑
        self.sandboxes: list[Sandbox] = [...]  # 多个工作台
        self._sandbox_labels: dict[int, str] = {...}  # 工作台标签

    async def execute_in_multiple_environments(self, task: str) -> dict:
        """跨环境执行

        1. 大脑规划各环境任务
        2. 分发到各 Sandbox 执行
        3. 大脑聚合结果
        """

    async def cross_environment_test(self, test_code: str) -> dict:
        """跨环境测试

        在 Python 和 Node.js 等多环境同时测试
        """
```

### MultiBrainMultiHandOrchestrator

```python
class MultiBrainMultiHandOrchestrator:
    """多脑多手: 多个 Claude + 多个 Sandbox + Session 协调"""

    def __init__(
        self,
        session: SessionEventStream,
        agent_sandbox_pairs: list[tuple[LLMClient, Sandbox]],
        message_bus: InterAgentMessageBus | None = None,
    ):
        self.session = session  # 共享协调中心
        self._pairs = agent_sandbox_pairs
        self._message_bus = message_bus

    async def coordinated_execution(self, task: str) -> CoordinationResult:
        """协调执行

        1. Session 记录任务
        2. 各组合独立执行（并行）
        3. 结果记录到 Session
        4. Session 协调合并
        """

    async def dynamic_task_assignment(self, task: str) -> dict:
        """动态任务分配

        根据执行进度动态调整任务分配
        """
```

### InterAgentMessageBus

```python
class InterAgentMessageBus:
    """智能体间消息传递总线"""

    def __init__(self, session: SessionEventStream):
        self.session = session
        self._message_handlers: dict[str, list[Callable]] = {}

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: dict,
    ) -> int:
        """发送消息（记录到 Session）"""

    async def receive_messages(self, agent_id: str) -> list[dict]:
        """接收消息（从 Session 筛选）"""

    async def broadcast(
        self,
        from_agent: str,
        message_type: str,
        content: dict,
    ) -> list[int]:
        """广播消息"""
```

---

## 协作工具集

### 会话管理工具

| 工具 | 功能 |
|------|------|
| `create_collaboration_session` | 创建协作会话 |
| `get_collaboration_status` | 获取协作状态 |
| `destroy_collaboration_session` | 销毁协作会话 |

### 多脑一手模式工具

| 工具 | 功能 |
|------|------|
| `setup_multi_brain_one_hand` | 设置多脑一手编排器 |
| `multi_angle_analysis` | 多角度分析 |
| `collaborative_improve` | 协作改进 |

### 一脑多手模式工具

| 工具 | 功能 |
|------|------|
| `setup_one_brain_multi_hand` | 设置一脑多手编排器 |
| `cross_environment_execute` | 跨环境执行 |
| `cross_environment_test` | 跨环境测试 |

### 多脑多手模式工具

| 工具 | 功能 |
|------|------|
| `setup_multi_brain_multi_hand` | 设置多脑多手编排器 |
| `coordinated_task` | 协调任务 |

### 消息传递工具

| 工具 | 功能 |
|------|------|
| `send_agent_message` | 发送智能体消息 |
| `broadcast_message` | 广播消息 |
| `receive_agent_messages` | 接收消息 |
| `register_message_handler` | 注册处理器 |

---

## 测试验证

### 测试覆盖

| 测试类 | 覆盖内容 |
|----------|----------|
| `TestCollaborationMode` | 协作模式枚举 |
| `TestAgentInstance` | 智能体实例 |
| `TestAnalysisResult` | 分析结果 |
| `TestMultiBrainOneHandOrchestrator` | 多脑一手编排器 |
| `TestOneBrainMultiHandOrchestrator` | 一脑多手编排器 |
| `TestMultiBrainMultiHandOrchestrator` | 多脑多手编排器 |
| `TestInterAgentMessageBus` | 消息总线 |
| `TestCollaborationTools` | 协作工具函数 |
| `TestIntegration` | 集成测试 |

### 验证标准

1. **多脑一手**: 多角度分析返回正确数量结果
2. **一脑多手**: 跨环境执行覆盖所有 Sandbox
3. **多脑多手**: Session 协调正确记录和合并
4. **消息总线**: 发送、接收、广播正确工作
5. **工具函数**: 会话创建、状态查询、销毁正确

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

## 使用示例

### 多脑一手：多角度代码分析

```python
from src.collaboration import MultiBrainOneHandOrchestrator
from src.llm_client import LLMClient
from src.sandbox import Sandbox

# 创建共享 Sandbox
sandbox = Sandbox(isolation_level=IsolationLevel.PROCESS)

# 创建多个大脑（不同模型）
security_client = LLMClient(gateway, "security/model")
performance_client = LLMClient(gateway, "performance/model")

# 创建编排器
orchestrator = MultiBrainOneHandOrchestrator(
    sandbox=sandbox,
    llm_clients=[security_client, performance_client],
    perspectives=["security", "performance"],
)

# 多角度分析
result = await orchestrator.analyze_from_multiple_angles("src/agent_loop.py")

# 协作改进
improve_result = await orchestrator.collaborative_improve("src/agent_loop.py")
```

### 一脑多手：跨环境测试

```python
from src.collaboration import OneBrainMultiHandOrchestrator

# 创建编排器
orchestrator = OneBrainMultiHandOrchestrator(
    llm_client=main_client,
    sandbox_configs=[
        {"isolation_level": "process"},  # Python
        {"isolation_level": "process"},  # Node.js
    ],
    labels=["python_env", "node_env"],
)

# 跨环境执行
result = await orchestrator.execute_in_multiple_environments(
    "Test API compatibility across environments"
)

# 跨环境测试
test_result = await orchestrator.cross_environment_test(test_code)
```

### 多脑多手：协调复杂任务

```python
from src.collaboration import MultiBrainMultiHandOrchestrator, InterAgentMessageBus
from src.session_event_stream import SessionEventStream

# 创建 Session
session = SessionEventStream("complex-task-session")

# 创建消息总线
message_bus = InterAgentMessageBus(session)
message_bus.set_pair_ids(["pair-1", "pair-2"])

# 创建编排器
orchestrator = MultiBrainMultiHandOrchestrator(
    session=session,
    agent_sandbox_pairs=[
        (client1, sandbox1),
        (client2, sandbox2),
    ],
    message_bus=message_bus,
)

# 协调执行
result = await orchestrator.coordinated_execution(
    "Implement user authentication module"
)

# 动态任务分配
dynamic_result = await orchestrator.dynamic_task_assignment(
    "Complex multi-step task"
)

# 发送消息
await message_bus.send_message("pair-1", "pair-2", "sync", {"progress": 50})

# 广播消息
await message_bus.broadcast("pair-1", "status_update", {"status": "completed"})
```

---

## 相关文档

- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Sandbox 隔离
- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 协调中心
- [src/collaboration.py](../src/collaboration.py) - 协作模块实现
- [src/tools/collaboration_tools.py](../src/tools/collaboration_tools.py) - 协作工具集