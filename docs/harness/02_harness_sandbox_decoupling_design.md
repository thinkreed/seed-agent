# 优化点 02: Harness/Sandbox 三件套解耦架构

> **版本**: v1.0  
> **创建日期**: 2026-05-03  
> **优先级**: 高  
> **依赖**: 01_session_event_stream_design  
> **参考来源**: Harness Engineering "智能体三件套解耦"

---

## 问题分析

### Harness Engineering 理念

**三件套解耦架构**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude (大脑)                             │
│                 负责推理和决策                                 │
│                 可替换、可多实例                               │
└─────────────────────────────────────────────────────────────┘
                            │ API 调用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Harness (双手)                            │
│       驱动运行循环 → 调用 Claude API → 路由工具调用            │
│                    本身无状态                                 │
│                 可随时创建、销毁、替换                          │
└─────────────────────────────────────────────────────────────┘
                            │ 工具执行路由
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox (工作台)                          │
│         隔离的文件系统、进程、网络执行环境                       │
│                    可重建、可扩展                              │
│                 可随时创建、销毁、替换                          │
└─────────────────────────────────────────────────────────────┘
```

**核心理念**: 
- **Claude**: 大脑，负责推理
- **Harness**: 双手，驱动循环，无状态
- **Sandbox**: 工作台，隔离执行

**关键性能优化**: 解耦后，大脑(推理)从容器(Sandbox)分离，首Token延迟降低 **60-90%**

### seed-agent 当前状态

**AgentLoop 高度耦合**:

```python
# 当前实现 (agent_loop.py)
class AgentLoop:
    def __init__(self, gateway, ...):
        self.gateway = gateway          # 直接持有 LLM 客户端
        self.history: list[dict] = []   # 状态嵌入在 AgentLoop
        self.tools = ToolRegistry()     # 直接持有工具执行器
    
    async def run(self, user_input: str):
        # 1. 构建上下文 (AgentLoop 内部)
        messages = self._build_messages()
        
        # 2. 直接调用 LLM (无中间层)
        response = await self.gateway.chat_completion(messages, tools=...)
        
        # 3. 直接执行工具 (无隔离)
        if response.get("tool_calls"):
            tool_results = await self._execute_tool_calls(response["tool_calls"])
        
        # 4. 直接修改历史 (状态耦合)
        self.history.append(response)
        self.history.extend(tool_results)
```

**问题**:
- AgentLoop 同时负责: 状态管理 + LLM调用 + 工具执行
- 无 Harness/Sandbox 分层
- 工具执行无隔离 (直接在进程内)
- 首Token延迟未优化

---

## 设计方案

### 1. 三件套架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    ClaudeClient (大脑)                       │
│                                                              │
│    - 封装 LLM Gateway                                        │
│    - 提供推理 API                                            │
│    - 可配置多个 Claude 实例                                   │
│    - 不持有状态                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ chat_completion()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Harness (控制器)                          │
│                                                              │
│    - 从 Session 拉取上下文                                    │
│    - 调用 ClaudeClient                                       │
│    - 路由工具调用到 Sandbox                                   │
│    - 记录响应到 Session                                       │
│    - 本身无状态 (可替换)                                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ execute_tools()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox (隔离执行环境)                     │
│                                                              │
│    - 隔离的文件系统                                           │
│    - 隔离的进程执行                                           │
│    - 隔离的网络策略                                           │
│    - 可重建、可销毁                                           │
│    - 不存储凭证                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2. ClaudeClient (大脑)

```python
class ClaudeClient:
    """Claude 大脑 - 负责推理"""
    
    def __init__(self, gateway: LLMGateway, model_id: str):
        self.gateway = gateway
        self.model_id = model_id
    
    async def reason(self, context: list[dict], tools: list[dict] = None) -> dict:
        """执行推理
        
        Args:
            context: 上下文消息 (从 Session 构建)
            tools: 可用工具 schema
        
        Returns:
            推理结果 (响应 + 可能的 tool_calls)
        """
        response = await self.gateway.chat_completion(
            self.model_id,
            context,
            tools=tools
        )
        return response
    
    async def stream_reason(self, context: list[dict], tools: list[dict] = None) -> AsyncGenerator:
        """流式推理"""
        async for chunk in self.gateway.stream_chat_completion(
            self.model_id, context, tools=tools
        ):
            yield chunk
```

### 3. Harness (控制器)

```python
class Harness:
    """Harness 控制器 - 无状态驱动"""
    
    def __init__(
        self,
        claude: ClaudeClient,
        session: SessionEventStream,
        sandbox: Sandbox,
    ):
        self.claude = claude      # 大脑
        self.session = session    # 只读访问状态
        self.sandbox = sandbox    # 执行环境
    
    async def run_cycle(self) -> dict:
        """执行一轮对话循环
        
        核心流程:
        1. 从 Session 拉取上下文
        2. 调用 Claude 推理
        3. 记录响应到 Session
        4. 如有工具调用，路由到 Sandbox 执行
        5. 记录工具结果到 Session
        """
        # 1. 从 Session 构建上下文
        context = self._build_context_from_session()
        
        # 2. 调用 Claude 推理
        response = await self.claude.reason(
            context,
            tools=self.sandbox.get_tool_schemas()
        )
        
        # 3. 记录响应
        self.session.emit_event("llm_response", response)
        
        # 4. 路由工具调用
        if response.get("tool_calls"):
            tool_results = await self._route_tool_calls(response["tool_calls"])
            self.session.emit_event("tool_result", {"results": tool_results})
            return {"response": response, "tool_results": tool_results, "continue": True}
        
        # 5. 无工具调用 = 对话完成
        return {"response": response, "continue": False}
    
    async def run_conversation(self, initial_prompt: str) -> str:
        """执行完整对话
        
        循环直到对话完成或达到上限
        """
        # 记录初始输入
        self.session.emit_event("user_input", {"content": initial_prompt})
        
        for iteration in range(MAX_ITERATIONS):
            cycle_result = await self.run_cycle()
            
            if not cycle_result["continue"]:
                return cycle_result["response"]["choices"][0]["message"]["content"]
        
        raise MaxIterationsExceeded()
    
    def _build_context_from_session(self) -> list[dict]:
        """从 Session 构建上下文 (关键: 无状态)"""
        # 使用摘要标记机制，不截断历史
        messages = []
        
        # 找最近的摘要标记
        last_summary = self._find_last_summary_marker()
        
        if last_summary:
            messages.append({
                "role": "system",
                "content": f"[历史摘要]\n{last_summary['data']['summary']}"
            })
        
        # 从摘要点后读取
        start_id = last_summary["id"] + 1 if last_summary else 0
        recent_events = self.session.get_events(start_id)
        
        for event in recent_events:
            messages.append(self._event_to_message(event))
        
        return messages
    
    async def _route_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """路由工具调用到 Sandbox"""
        results = await self.sandbox.execute_tools(tool_calls)
        return results
```

### 4. Sandbox (隔离执行环境)

```python
class Sandbox:
    """隔离的执行沙盒"""
    
    ISOLATION_LEVELS = {
        "process": "进程级隔离 (子进程执行)",
        "container": "容器级隔离 (Docker)",
        "vm": "虚拟机级隔离 (最强)",
    }
    
    def __init__(
        self,
        isolation_level: str = "process",
        file_system_root: Path = None,
        network_policy: dict = None,
    ):
        self.isolation_level = isolation_level
        self._fs_root = file_system_root or Path("~/.seed/sandbox/")
        self._network_policy = network_policy or {"allow": [], "deny": ["*"]}
        self._tools = ToolRegistry()
        self._credential_proxy: CredentialProxy = None  # 凭证代理
    
    def register_tools(self, tool_registry: ToolRegistry) -> None:
        """注册可用工具"""
        self._tools = tool_registry
    
    def get_tool_schemas(self) -> list[dict]:
        """获取工具 schema"""
        return self._tools.get_schemas()
    
    async def execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """在隔离环境中执行工具
        
        Args:
            tool_calls: 工具调用列表
        
        Returns:
            执行结果列表
        """
        results = []
        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)
        return results
    
    async def _execute_single_tool(self, tool_call: dict) -> dict:
        """执行单个工具"""
        tool_name = tool_call["function"]["name"]
        tool_args = json.loads(tool_call["function"]["arguments"])
        
        # 1. 路径映射: 沙盒内 → 主机
        mapped_args = self._map_paths(tool_args)
        
        # 2. 权限检查
        if not self._check_permission(tool_name, mapped_args):
            return {
                "tool_call_id": tool_call["id"],
                "error": "Permission denied in sandbox"
            }
        
        # 3. 根据隔离级别执行
        if self.isolation_level == "process":
            result = await self._execute_in_subprocess(tool_name, mapped_args)
        elif self.isolation_level == "container":
            result = await self._execute_in_container(tool_name, mapped_args)
        else:
            result = await self._execute_in_process(tool_name, mapped_args)
        
        return {
            "tool_call_id": tool_call["id"],
            "result": result
        }
    
    def _map_paths(self, args: dict) -> dict:
        """路径映射
        
        沙盒内路径: /workspace/file.txt
        主机路径: ~/.seed/sandbox/workspace/file.txt
        """
        mapped = {}
        for key, value in args.items():
            if key in ["path", "file_path", "directory"] and isinstance(value, str):
                # 映射沙盒路径到主机路径
                if value.startswith("/workspace/"):
                    mapped[key] = str(self._fs_root / value[11:])
                elif value.startswith("/"):
                    mapped[key] = str(self._fs_root / value[1:])
                else:
                    mapped[key] = value
            else:
                mapped[key] = value
        return mapped
    
    async def _execute_in_subprocess(self, tool_name: str, args: dict) -> str:
        """进程级隔离执行"""
        # 创建子进程执行
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", 
            f"from tools import {tool_name}; print({tool_name}(**{args}))",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode() if stdout else stderr.decode()
    
    # === 容器级隔离 (可选) ===
    
    async def _execute_in_container(self, tool_name: str, args: dict) -> str:
        """Docker 容器级隔离"""
        import docker
        client = docker.from_env()
        
        # 创建临时容器
        container = client.containers.run(
            "seed-agent-sandbox:latest",
            f"python -c 'from tools import {tool_name}; {tool_name}(**{args})'",
            volumes={str(self._fs_root): {"bind": "/workspace", "mode": "rw"}},
            remove=True,
        )
        return container
```

### 5. 多实例支持

```python
class HarnessManager:
    """Harness 管理器 - 支持多实例"""
    
    def __init__(self):
        self._harnesses: dict[str, Harness] = {}
        self._sandboxes: dict[str, Sandbox] = {}
    
    def create_harness(
        self,
        harness_id: str,
        claude_config: dict,
        sandbox_config: dict,
    ) -> Harness:
        """创建新的 Harness 实例"""
        claude = ClaudeClient(
            LLMGateway(claude_config["gateway_config"]),
            claude_config["model_id"]
        )
        sandbox = Sandbox(**sandbox_config)
        session = SessionEventStream(harness_id, Path("~/.seed/sessions/"))
        
        harness = Harness(claude, session, sandbox)
        self._harnesses[harness_id] = harness
        self._sandboxes[harness_id] = sandbox
        
        return harness
    
    def destroy_harness(self, harness_id: str) -> None:
        """销毁 Harness (牲畜可替换)"""
        if harness_id in self._harnesses:
            del self._harnesses[harness_id]
        if harness_id in self._sandboxes:
            self._sandboxes[harness_id].cleanup()
            del self._sandboxes[harness_id]
```

---

## 实施步骤

### Phase 1: ClaudeClient 提取 (1天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 从 AgentLoop 提取 LLM 调用逻辑 | ClaudeClient 可独立调用 |
| 1.2 | 封装 gateway.chat_completion | 接口不变 |
| 1.3 | 单元测试 | 推理 API 正常工作 |

### Phase 2: Sandbox 实现 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 实现进程级隔离执行 | 子进程执行工具 |
| 2.2 | 实现路径映射 | 沙盒路径正确映射 |
| 2.3 | 实现权限检查 | 禁止危险操作 |
| 2.4 | 工具注册机制 | sandbox.get_tool_schemas() |

### Phase 3: Harness 集成 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | 实现 Harness.run_cycle() | 单轮对话正常 |
| 3.2 | 集成 SessionEventStream | 从事件流构建上下文 |
| 3.3 | 工具路由机制 | 正确路由到 Sandbox |
| 3.4 | 集成测试 | 完整对话流程 |

### Phase 4: AgentLoop 改造 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 4.1 | AgentLoop 使用 Harness | AgentLoop.harness.run() |
| 4.2 | 移除状态管理 | AgentLoop 不再持有 history |
| 4.3 | backward compatibility | 现有接口兼容 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **首Token延迟优化** | 60-90% 降低 (大脑与容器解耦) |
| **无状态 Harness** | 可随时替换，不影响 Session |
| **执行隔离** | Sandbox 隔离，安全可控 |
| **多实例支持** | 多 Claude + 多 Sandbox 协作 |
| **可重建性** | Sandbox 可随时销毁重建 |

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 进程隔离开销 | 执行速度下降 | 使用 async subprocess |
| 容器依赖 | 需要 Docker | 进程级作为默认 |
| 接口变化 | 现有代码兼容 | 提供 backward compatibility wrapper |

---

## 测试计划

```python
def test_harness_sandbox_decoupling():
    # 创建三件套
    claude = ClaudeClient(LLMGateway(config), "qwen-coder-plus")
    session = SessionEventStream("test", Path("/tmp/test"))
    sandbox = Sandbox(isolation_level="process")
    sandbox.register_tools(ToolRegistry())
    
    harness = Harness(claude, session, sandbox)
    
    # 测试对话循环
    result = await harness.run_conversation("hello")
    assert result is not None
    
    # 测试工具路由
    session.emit_event("tool_call", {"function": {"name": "file_read"}})
    cycle_result = await harness.run_cycle()
    assert "tool_results" in cycle_result

def test_sandbox_isolation():
    sandbox = Sandbox(isolation_level="process", file_system_root=Path("/tmp/sandbox"))
    
    # 测试路径映射
    mapped = sandbox._map_paths({"path": "/workspace/test.txt"})
    assert mapped["path"] == "/tmp/sandbox/test.txt"
    
    # 测试权限检查
    allowed = sandbox._check_permission("file_read", {"path": "/tmp/sandbox/test.txt"})
    assert allowed
```

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流
- [08_credential_security_design.md](08_credential_security_design.md) - 凭证安全架构
- [06_multi_agent_collaboration_design.md](06_multi_agent_collaboration_design.md) - 多智能体协作