# 优化点 02: Harness/Sandbox 三件套解耦架构

> **版本**: v2.0 (已落地实现)
> **创建日期**: 2026-05-03
> **实现日期**: 2026-05-03
> **优先级**: 高
> **状态**: ✅ 已完成
> **参考来源**: Harness Engineering "智能体三件套解耦"

---

## 实现状态

### ✅ 已完成模块

| 模块 | 文件 | 实现状态 |
|------|------|----------|
| **LLMClient** | `src/llm_client.py` | ✅ 已实现，含 LLMClientPool |
| **Harness** | `src/harness.py` | ✅ 已实现，含 HarnessManager |
| **Sandbox** | `src/sandbox.py` | ✅ 已实现，含权限系统 |
| **AgentLoop** | `src/agent_loop.py` | ✅ 已重写，纯三件套架构 |
| **SessionEventStream** | `src/session_event_stream.py` | ✅ 已实现，不可变事件流 |
| **测试** | `tests/test_*.py` | ✅ 已更新 |

### 关键变更

1. **移除 legacy 代码**: AgentLoop 不再有 `_run_legacy` 方法
2. **强制三件套**: AgentLoop 初始化必须创建 LLMClient/Harness/Sandbox
3. **无向后兼容**: 移除 `use_harness` 参数
4. **纯事件流**: Session 替代 history 可变列表

---

## 落地架构

### 三件套解耦

```
┌─────────────────────────────────────────────────────────────┐
│                    LLMClient (大脑)                          │
│                                                              │
│    - 封装 LLM Gateway                                        │
│    - 提供 reason() / stream_reason() API                    │
│    - 支持多模型实例 (LLMClientPool)                          │
│    - OpenTelemetry 集成                                      │
│    - 不持有状态                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ reason() / stream_reason()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Harness (控制器)                          │
│                                                              │
│    - 从 SessionEventStream 拉取上下文                        │
│    - 调用 LLMClient.reason()                                │
│    - 路由工具调用到 Sandbox                                   │
│    - 记录事件到 SessionEventStream                           │
│    - 工具执行指标追踪                                         │
│    - 本身无状态 (可替换)                                      │
│    - HarnessManager 支持多实例                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ execute_tools()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox (工作台)                          │
│                                                              │
│    - 隔离的文件系统访问                                       │
│    - 隔离的进程执行                                           │
│    - 隔离的网络策略                                           │
│    - 路径映射 (沙盒 → 主机)                                   │
│    - 权限检查 (PermissionAction)                             │
│    - 输出截断                                                │
│    - 凭证代理 (不存储凭证)                                    │
└─────────────────────────────────────────────────────────────┘
```

### 集成架构

```python
class AgentLoop:
    """主执行引擎 - 纯三件套架构"""
    
    def __init__(self, gateway, model_id, ...):
        # 1. SessionEventStream (宠物，不可丢失)
        self.session = SessionEventStream(session_id)
        
        # 2. LLMClient (大脑)
        self.llm_client = LLMClient(gateway, model_id)
        
        # 3. Sandbox (工作台)
        self.sandbox = Sandbox(isolation_level)
        self.sandbox.register_tools(self.tools)
        
        # 4. Harness (控制器)
        self.harness = Harness(
            llm_client=self.llm_client,
            session=self.session,
            sandbox=self.sandbox
        )
    
    async def run(self, user_input: str) -> str:
        """执行对话 - 使用 Harness"""
        result = await self.harness.run_conversation(user_input)
        await self._maybe_summarize()  # 摘要触发
        return result
    
    async def stream_run(self, user_input: str) -> AsyncGenerator:
        """流式执行 - 使用 Harness"""
        async for chunk in self.harness.stream_conversation(user_input):
            yield chunk
```

---

## 实现细节

### LLMClient (大脑)

```python
class LLMClient:
    """LLM 大脑 - 负责推理，无状态"""
    
    def __init__(self, gateway: LLMGateway, model_id: str):
        self.gateway = gateway
        self.model_id = model_id
        self._model_config = gateway.get_model_config(model_id)
    
    async def reason(
        self,
        context: list[dict],
        tools: list[dict] | None = None,
        priority: int | None = None,
        **kwargs
    ) -> dict[str, Any]:
        """执行推理"""
        response = await self.gateway.chat_completion(
            self.model_id,
            context,
            priority=priority or self.default_priority,
            tools=tools,
            **kwargs
        )
        return response
    
    async def stream_reason(...) -> AsyncGenerator[dict, None]:
        """流式推理"""
        async for chunk in self.gateway.stream_chat_completion(...):
            yield chunk
    
    def get_context_window(self) -> int:
        """获取模型上下文窗口"""
        return self._model_config.contextWindow
    
    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""


class LLMClientPool:
    """LLM 客户端池 - 支持多模型实例"""
    
    def add_client(self, model_id: str, is_primary: bool = False) -> LLMClient:
        """添加 LLM 客户端"""
    
    async def reason_with_fallback(
        self,
        context: list[dict],
        fallback_models: list[str] | None = None
    ) -> dict[str, Any]:
        """带故障转移的推理"""
```

### Harness (控制器)

```python
class Harness:
    """Harness 控制器 - 无状态驱动"""
    
    def __init__(
        self,
        llm_client: LLMClient,
        session: SessionEventStream,
        sandbox: Sandbox,
        max_iterations: int = 30
    ):
        self.llm_client = llm_client      # 大脑
        self.session = session            # 状态（只读访问）
        self.sandbox = sandbox            # 执行环境
        self._metrics: list[ToolExecutionMetrics] = []
    
    async def run_cycle(self, priority: int) -> CycleResult:
        """执行一轮对话循环
        
        1. 从 Session 构建上下文（无状态关键）
        2. 调用 LLM 推理
        3. 记录响应到 Session
        4. 路由工具调用到 Sandbox
        5. 记录工具结果到 Session
        """
        context = self._build_context_from_session()
        response = await self.llm_client.reason(context, tools=self.sandbox.get_tool_schemas())
        
        self.session.emit_event(EventType.LLM_RESPONSE, response)
        
        if response.get("tool_calls"):
            tool_results = await self._route_tool_calls(response["tool_calls"])
            return {"response": response, "tool_results": tool_results, "continue_loop": True}
        
        return {"response": response, "tool_results": None, "continue_loop": False}
    
    async def run_conversation(self, initial_prompt: str) -> str:
        """执行完整对话"""
        self.session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})
        
        for iteration in range(self.max_iterations):
            cycle_result = await self.run_cycle(priority)
            if not cycle_result["continue_loop"]:
                return cycle_result["response"]["choices"][0]["message"]["content"]
        
        raise MaxIterationsExceeded(iteration)
    
    async def stream_conversation(self, initial_prompt: str) -> AsyncGenerator:
        """流式执行对话"""
    
    def get_metrics(self) -> list[ToolExecutionMetrics]:
        """获取工具执行指标"""


class HarnessManager:
    """Harness 管理器 - 支持多实例"""
    
    def create_harness(self, harness_id: str, model_id: str) -> Harness:
        """创建新的 Harness 实例"""
    
    def destroy_harness(self, harness_id: str) -> bool:
        """销毁 Harness（牲畜可替换）"""
    
    def get_total_metrics(self) -> dict[str, Any]:
        """获取所有 Harness 的总指标"""
```

### Sandbox (工作台)

```python
class IsolationLevel(str, Enum):
    """隔离级别"""
    PROCESS = "process"       # 进程级隔离
    CONTAINER = "container"   # 容器级隔离
    VM = "vm"                 # 虚拟机级隔离


class PermissionAction(str, Enum):
    """权限动作"""
    ALLOW = "allow"
    DENY = "deny"
    READONLY = "readonly"


class Sandbox:
    """隔离的执行沙盒"""
    
    PATH_KEYS = [
        "path", "file_path", "directory", "dir",
        "src", "dst", "source", "destination"
    ]
    
    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        file_system_root: Path | None = None,
        workspace_path: Path | None = None
    ):
        self.isolation_level = isolation_level
        self._fs_root = file_system_root or DEFAULT_SANDBOX_ROOT
        self._workspace_path = workspace_path or Path.cwd()
        self._permissions = self.DEFAULT_PERMISSIONS.copy()
    
    def register_tools(self, tool_registry: ToolRegistry) -> None:
        """注册可用工具"""
        self._tools = tool_registry
    
    def get_tool_schemas(self) -> list[dict]:
        """获取工具 schema"""
        return self._tools.get_schemas()
    
    async def execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """在隔离环境中执行工具"""
        results = []
        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)
        return results
    
    def _map_paths(self, args: dict) -> dict:
        """路径映射：沙盒内路径 → 主机路径
        
        - /workspace/... → {workspace_path}/...
        - /sandbox/... → {fs_root}/...
        """
    
    def _check_permission(self, tool_name: str, args: dict) -> bool:
        """检查工具执行权限"""
    
    def set_permission(self, tool_name: str, action: PermissionAction) -> None:
        """设置单个工具权限"""
    
    def deny_all_tools(self) -> None:
        """拒绝所有工具（用于只读模式）"""
    
    def allow_readonly_tools(self) -> None:
        """只允许只读工具"""
    
    def set_credential_proxy(self, proxy: Any) -> None:
        """设置凭证代理（不存储凭证）"""
```

---

## 测试验证

### 测试覆盖

| 测试文件 | 覆盖模块 |
|----------|----------|
| `tests/test_llm_client.py` | LLMClient, LLMClientPool |
| `tests/test_harness.py` | Harness, HarnessManager, MaxIterationsExceeded |
| `tests/test_sandbox.py` | Sandbox, IsolationLevel, PermissionAction |
| `tests/test_agent_loop.py` | AgentLoop 三件套集成 |

### 验证标准

1. **三件套初始化**: AgentLoop 必须创建 llm_client/harness/sandbox
2. **无 legacy 代码**: 无 `_run_legacy` 方法调用
3. **事件流正确**: 所有事件记录到 SessionEventStream
4. **路径映射正确**: 沙盒路径正确映射到主机路径
5. **权限检查生效**: deny 工具返回 "Permission denied"
6. **指标追踪**: Harness.get_metrics() 返回工具执行指标

---

## 性能收益

| 收益 | 描述 |
|------|------|
| **首Token延迟优化** | 60-90% 降低 (大脑与容器解耦) |
| **无状态 Harness** | 可随时替换，不影响 Session |
| **执行隔离** | Sandbox 隔离，安全可控 |
| **多实例支持** | 多 LLMClient + 多 Sandbox 协作 |
| **可重建性** | Sandbox/Harness 可随时销毁重建 |

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流
- [08_credential_security_design.md](08_credential_security_design.md) - 凭证安全架构
- [06_multi_agent_collaboration_design.md](06_multi_agent_collaboration_design.md) - 多智能体协作
- [src/llm_client.py](../src/llm_client.py) - LLMClient 实现
- [src/harness.py](../src/harness.py) - Harness 实现
- [src/sandbox.py](../src/sandbox.py) - Sandbox 实现