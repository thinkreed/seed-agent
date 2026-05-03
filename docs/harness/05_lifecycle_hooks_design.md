# 优化点 05: 确定性生命周期钩子体系

> **版本**: v1.0  
> **创建日期**: 2026-05-03  
> **优先级**: 中  
> **依赖**: 01_session_event_stream_design, 02_harness_sandbox_decoupling_design  
> **参考来源**: Harness Engineering "确定性生命周期钩子"

---

## 问题分析

### Harness Engineering 理念

**确定性生命周期钩子**: 
> 在智能体生命周期的关键节点自动触发预设动作（如代码格式化），由系统确保关键流程被执行，不依赖可能被模型遗忘的指令

**关键节点**:

| 钩子节点 | 触发时机 | 预设动作示例 |
|----------|----------|-------------|
| `session_start` | 会话开始 | 加载记忆索引、初始化上下文 |
| `tool_call_before` | 工具调用前 | 代码格式化、权限检查 |
| `tool_call_after` | 工具调用后 | 结果验证、日志记录 |
| `response_before` | 响应生成前 | 上下文裁剪、格式检查 |
| `response_after` | 响应生成后 | 记忆整理、摘要生成 |
| `session_end` | 会话结束 | 状态持久化、归档 L5 |

### seed-agent 当前状态

**已有的钩子实现**:

| 钩子 | 实现位置 | 状态 |
|------|----------|------|
| `autodream` | Scheduler (12小时) | ✅ 已有 |
| `autonomous_explore` | AutonomousExplorer (2小时空闲) | ✅ 已有 |
| `_maybe_summarize` | AgentLoop (轮数/阈值触发) | ⚠️ 部分 |
| OpenTelemetry Span | `_run_single_tool_call` | ⚠️ 部分 |

**问题**:
- ❌ 钩子散落在各模块，无统一注册体系
- ❌ 缺少关键节点钩子 (tool_call_before/after, response_before/after)
- ❌ 无法动态注册自定义钩子
- ❌ 钩子执行无优先级管理
- ❌ 钩子失败处理不完善

---

## 设计方案

### 1. 生命周期钩子注册体系

```python
class LifecycleHookRegistry:
    """确定性生命周期钩子注册中心"""
    
    HOOK_POINTS = {
        # 会话生命周期
        "session_start": "会话开始",
        "session_end": "会话结束",
        "session_pause": "会话暂停",
        "session_resume": "会话恢复",
        
        # 工具执行生命周期
        "tool_call_before": "工具调用前",
        "tool_call_after": "工具调用后",
        "tool_call_error": "工具调用错误",
        
        # LLM 调用生命周期
        "llm_call_before": "LLM 调用前",
        "llm_call_after": "LLM 调用后",
        "llm_stream_start": "LLM 流式响应开始",
        "llm_stream_chunk": "LLM 流式响应块",
        "llm_stream_end": "LLM 流式响应结束",
        
        # 响应生命周期
        "response_before": "响应生成前",
        "response_after": "响应生成后",
        
        # 上下文生命周期
        "context_reset_before": "上下文重置前",
        "context_reset_after": "上下文重置后",
        "summary_generated": "摘要生成后",
        
        # 子代理生命周期
        "subagent_spawn": "子代理创建",
        "subagent_start": "子代理开始执行",
        "subagent_end": "子代理执行结束",
        "subagent_error": "子代理执行错误",
        
        # Ralph Loop 生命周期
        "ralph_iteration_start": "Ralph 迭代开始",
        "ralph_iteration_end": "Ralph 迭代结束",
        "ralph_completion_check": "Ralph 完成检查",
        "ralph_context_reset": "Ralph 上下文重置",
    }
    
    def __init__(self):
        self._hooks: dict[str, list[tuple[int, Callable]]] = {
            point: [] for point in self.HOOK_POINTS
        }
        self._hook_stats: dict[str, dict] = {}  # 执行统计
    
    # === 注册 ===
    
    def register(
        self,
        hook_point: str,
        callback: Callable,
        priority: int = 0,
        name: str = None,
    ) -> str:
        """注册钩子
        
        Args:
            hook_point: 钩子节点名称
            callback: 钩子回调函数 (接受 context 参数)
            priority: 执行优先级 (数值越小越先执行)
            name: 钩子名称 (用于标识)
        
        Returns:
            hook_id: 钩子唯一标识
        """
        if hook_point not in self.HOOK_POINTS:
            raise ValueError(f"Unknown hook point: {hook_point}")
        
        hook_id = name or f"{hook_point}_{len(self._hooks[hook_point])}"
        
        self._hooks[hook_point].append((priority, callback, hook_id))
        self._hooks[hook_point].sort(key=lambda x: x[0])  # 按优先级排序
        
        self._hook_stats[hook_id] = {
            "point": hook_point,
            "priority": priority,
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "last_call_time": None,
        }
        
        logger.info(f"Hook registered: {hook_id} at {hook_point} (priority={priority})")
        return hook_id
    
    def unregister(self, hook_id: str) -> bool:
        """注销钩子"""
        for hook_point, hooks in self._hooks.items():
            for i, (priority, callback, id_) in enumerate(hooks):
                if id_ == hook_id:
                    hooks.pop(i)
                    logger.info(f"Hook unregistered: {hook_id}")
                    return True
        return False
    
    # === 触发 ===
    
    async def trigger(self, hook_point: str, context: dict) -> dict:
        """触发钩子
        
        Args:
            hook_point: 钩子节点名称
            context: 钩子上下文数据
        
        Returns:
            执行报告
        """
        if hook_point not in self._hooks:
            return {"status": "unknown_point", "hooks_executed": 0}
        
        hooks = self._hooks[hook_point]
        report = {
            "hook_point": hook_point,
            "hooks_count": len(hooks),
            "hooks_executed": 0,
            "hooks_failed": 0,
            "results": [],
        }
        
        for priority, callback, hook_id in hooks:
            start_time = time.time()
            
            try:
                # 执行钩子
                if asyncio.iscoroutinefunction(callback):
                    result = await callback(context)
                else:
                    result = callback(context)
                
                # 更新统计
                self._hook_stats[hook_id]["total_calls"] += 1
                self._hook_stats[hook_id]["success_calls"] += 1
                self._hook_stats[hook_id]["last_call_time"] = time.time()
                
                report["hooks_executed"] += 1
                report["results"].append({
                    "hook_id": hook_id,
                    "status": "success",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "result": result,
                })
                
            except Exception as e:
                # 钩子失败处理
                self._hook_stats[hook_id]["total_calls"] += 1
                self._hook_stats[hook_id]["failed_calls"] += 1
                
                report["hooks_failed"] += 1
                report["results"].append({
                    "hook_id": hook_id,
                    "status": "failed",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "error": str(e),
                })
                
                logger.warning(f"Hook {hook_id} failed: {type(e).__name__}: {e}")
        
        return report
    
    # === 查询 ===
    
    def list_hooks(self, hook_point: str = None) -> list[dict]:
        """列出已注册钩子"""
        if hook_point:
            return [
                {"hook_id": id_, "priority": pri, "callback": str(cb)}
                for pri, cb, id_ in self._hooks.get(hook_point, [])
            ]
        
        return [
            {"hook_point": point, "hook_id": id_, "priority": pri}
            for point, hooks in self._hooks.items()
            for pri, cb, id_ in hooks
        ]
    
    def get_hook_stats(self, hook_id: str) -> dict:
        """获取钩子执行统计"""
        return self._hook_stats.get(hook_id, {})
```

### 2. 内置钩子定义

```python
def register_builtin_hooks(registry: LifecycleHookRegistry) -> None:
    """注册内置钩子"""
    
    # === 会话生命周期 ===
    
    @registry.register("session_start", priority=0)
    async def load_memory_index(context: dict) -> None:
        """加载 L1 记忆索引"""
        agent = context.get("agent")
        if agent:
            index = agent.tools.execute("read_memory_index")
            context["session"]["memory_index"] = index
    
    @registry.register("session_end", priority=0)
    async def persist_session_state(context: dict) -> None:
        """持久化会话状态"""
        session = context.get("session")
        if session:
            session.persist_state()
    
    @registry.register("session_end", priority=1)
    async def archive_to_l5(context: dict) -> None:
        """归档到 L5"""
        session = context.get("session")
        archive_layer = context.get("archive_layer")
        if session and archive_layer:
            await archive_layer.archive_session(session)
    
    # === 工具执行生命周期 ===
    
    @registry.register("tool_call_before", priority=0)
    def check_tool_permission(context: dict) -> bool:
        """检查工具调用权限"""
        tool_name = context.get("tool_name")
        permission_set = context.get("permission_set")
        
        if permission_set and tool_name not in permission_set:
            raise PermissionError(f"Tool {tool_name} not allowed in {permission_set}")
        
        return True
    
    @registry.register("tool_call_before", priority=1)
    def log_tool_call(context: dict) -> None:
        """记录工具调用"""
        tool_name = context.get("tool_name")
        tool_args = context.get("tool_args")
        logger.info(f"Tool call: {tool_name} with args {tool_args}")
    
    @registry.register("tool_call_after", priority=0)
    def validate_tool_result(context: dict) -> None:
        """验证工具结果"""
        result = context.get("result")
        if isinstance(result, str) and "Error" in result:
            logger.warning(f"Tool execution error: {result}")
    
    @registry.register("tool_call_after", priority=1)
    def record_to_memory_graph(context: dict) -> None:
        """记录到 Memory Graph"""
        tool_name = context.get("tool_name")
        result = context.get("result")
        
        if tool_name == "load_skill":
            skill_name = context.get("tool_args", {}).get("name")
            outcome = "success" if "Error" not in str(result) else "failed"
            # record_skill_outcome(skill_name, outcome, ...)
    
    # === LLM 调用生命周期 ===
    
    @registry.register("llm_call_before", priority=0)
    def apply_context_pruning(context: dict) -> None:
        """应用上下文裁剪"""
        messages = context.get("messages")
        pruner = context.get("pruner")
        task = context.get("current_task")
        
        if pruner and task:
            context["pruned_messages"] = pruner.prune_for_task(messages, task)
    
    @registry.register("llm_call_after", priority=0)
    def validate_llm_response(context: dict) -> None:
        """验证 LLM 响应"""
        response = context.get("response")
        
        if not response.get("choices"):
            raise ValueError("Empty LLM response")
    
    # === 响应生命周期 ===
    
    @registry.register("response_after", priority=0)
    async def generate_summary_if_needed(context: dict) -> None:
        """生成摘要 (如需要)"""
        session = context.get("session")
        compressor = context.get("compressor")
        
        if compressor and session:
            usage_ratio = session.get_context_usage_ratio()
            if usage_ratio > 0.75:
                await compressor.compress(session, session.context_window)
    
    @registry.register("response_after", priority=1)
    def extract_user_feedback(context: dict) -> None:
        """提取用户反馈"""
        user_modeling = context.get("user_modeling")
        interaction = context.get("interaction")
        
        if user_modeling and interaction:
            user_modeling.observe_from_interaction(interaction)
    
    # === 上下文生命周期 ===
    
    @registry.register("context_reset_before", priority=0)
    def extract_critical_context(context: dict) -> str:
        """提取关键上下文"""
        history = context.get("history")
        return extract_critical_context(history)
    
    @registry.register("context_reset_after", priority=0)
    def inject_preserved_context(context: dict) -> None:
        """注入保留上下文"""
        preserved = context.get("preserved_context")
        history = context.get("history")
        
        if preserved:
            history.append({
                "role": "system",
                "content": f"[状态摘要]\n{preserved}"
            })
    
    # === Ralph Loop 生命周期 ===
    
    @registry.register("ralph_iteration_end", priority=0)
    def persist_ralph_state(context: dict) -> None:
        """持久化 Ralph 状态"""
        ralph = context.get("ralph_loop")
        response = context.get("response")
        
        if ralph:
            ralph._persist_state(response)
    
    @registry.register("ralph_completion_check", priority=0)
    def check_external_verification(context: dict) -> bool:
        """外部验证检查"""
        completion_type = context.get("completion_type")
        criteria = context.get("completion_criteria")
        
        # 执行相应验证
        return check_completion(completion_type, criteria)
```

### 3. 集成到 Harness

```python
class HarnessWithHooks:
    """带生命周期钩子的 Harness"""
    
    def __init__(
        self,
        claude: ClaudeClient,
        session: SessionEventStream,
        sandbox: Sandbox,
        hook_registry: LifecycleHookRegistry,
    ):
        self.claude = claude
        self.session = session
        self.sandbox = sandbox
        self.hook_registry = hook_registry
    
    async def run_cycle(self) -> dict:
        """执行一轮对话循环 (带钩子)"""
        context = {
            "session": self.session,
            "claude": self.claude,
            "sandbox": self.sandbox,
        }
        
        # 1. 触发 llm_call_before
        await self.hook_registry.trigger("llm_call_before", context)
        
        # 2. 构建上下文
        messages = self._build_context_from_session()
        context["messages"] = messages
        
        # 3. 触发 response_before
        await self.hook_registry.trigger("response_before", context)
        
        # 4. 调用 LLM
        response = await self.claude.reason(context.get("pruned_messages") or messages)
        context["response"] = response
        
        # 5. 触发 llm_call_after
        await self.hook_registry.trigger("llm_call_after", context)
        
        # 6. 记录响应
        self.session.emit_event("llm_response", response)
        
        # 7. 如果有工具调用
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                tool_context = {
                    **context,
                    "tool_name": tc["function"]["name"],
                    "tool_args": json.loads(tc["function"]["arguments"]),
                    "tool_call_id": tc["id"],
                }
                
                # 工具调用前钩子
                await self.hook_registry.trigger("tool_call_before", tool_context)
                
                # 执行工具
                result = await self.sandbox.execute_tool(tc)
                tool_context["result"] = result
                
                # 工具调用后钩子
                await self.hook_registry.trigger("tool_call_after", tool_context)
                
                self.session.emit_event("tool_result", {"id": tc["id"], "result": result})
        
        # 8. 触发 response_after
        await self.hook_registry.trigger("response_after", context)
        
        return {"response": response, "continue": response.get("tool_calls") is not None}
    
    async def run_conversation(self, initial_prompt: str) -> str:
        """执行完整对话"""
        # 1. 会话开始钩子
        start_context = {"session": self.session, "agent": self}
        await self.hook_registry.trigger("session_start", start_context)
        
        # 记录初始输入
        self.session.emit_event("user_input", {"content": initial_prompt})
        
        for iteration in range(MAX_ITERATIONS):
            cycle_result = await self.run_cycle()
            
            if not cycle_result["continue"]:
                break
        
        # 2. 会话结束钩子
        end_context = {"session": self.session, "response": cycle_result["response"]}
        await self.hook_registry.trigger("session_end", end_context)
        
        return cycle_result["response"]["choices"][0]["message"]["content"]
```

---

## 实施步骤

### Phase 1: 钩子注册体系 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 实现 LifecycleHookRegistry 类 | register/unregister/trigger |
| 1.2 | 实现钩子统计 | get_hook_stats |
| 1.3 | 单元测试 | 钩子注册触发正确 |

### Phase 2: 内置钩子实现 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 实现会话生命周期钩子 | session_start/end |
| 2.2 | 实现工具执行钩子 | tool_call_before/after |
| 2.3 | 实现响应钩子 | response_before/after |
| 2.4 | 实现上下文钩子 | context_reset_before/after |
| 2.5 | 集成测试 | 所有钩子正确触发 |

### Phase 3: Harness 集成 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | HarnessWithHooks 实现 | run_cycle 带钩子 |
| 3.2 | 钩子上下文传递 | context 参数正确 |
| 3.3 | backward compatibility | 现有 AgentLoop 兼容 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **流程自动化增强** | 关键节点自动执行预设动作 |
| **钩子可扩展** | 动态注册自定义钩子 |
| **优先级管理** | 钩子按优先级有序执行 |
| **执行统计** | 钩子执行次数/成功/失败统计 |
| **失败处理** | 钩子失败不中断主流程 |

---

## 测试计划

```python
def test_hook_registry():
    registry = LifecycleHookRegistry()
    
    # 注册钩子
    hook_id = registry.register("tool_call_before", lambda ctx: True, priority=0)
    
    # 触发钩子
    report = await registry.trigger("tool_call_before", {"tool_name": "file_read"})
    
    assert report["hooks_executed"] == 1
    assert report["hooks_failed"] == 0
    
    # 查询统计
    stats = registry.get_hook_stats(hook_id)
    assert stats["total_calls"] == 1
    assert stats["success_calls"] == 1

def test_builtin_hooks():
    registry = LifecycleHookRegistry()
    register_builtin_hooks(registry)
    
    # 验证内置钩子注册
    hooks = registry.list_hooks()
    
    assert len(hooks) > 0
    assert any(h["hook_point"] == "session_start" for h in hooks)
    assert any(h["hook_point"] == "tool_call_before" for h in hooks)

def test_harness_with_hooks():
    registry = LifecycleHookRegistry()
    register_builtin_hooks(registry)
    
    harness = HarnessWithHooks(claude, session, sandbox, registry)
    
    # 执行对话
    result = await harness.run_conversation("hello")
    
    # 验证钩子触发
    assert registry.get_hook_stats("session_start_0")["total_calls"] == 1
    assert registry.get_hook_stats("session_end_0")["total_calls"] == 1
```

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流
- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Harness 集成
- [03_memory_system_upgrade_design.md](03_memory_system_upgrade_design.md) - L5 归档钩子