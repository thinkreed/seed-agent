# 优化点 04: 渐进式上下文压缩 + 智能裁剪

> **版本**: v1.0  
> **创建日期**: 2026-05-03  
> **优先级**: 中  
> **依赖**: 01_session_event_stream_design  
> **参考来源**: Harness Engineering "上下文工程"

---

## 问题分析

### Harness Engineering 上下文工程模式

| 模式 | 描述 |
|------|------|
| **上下文压缩** | 上下文窗口将满时，将早期对话压缩成总结 |
| **记忆工具** | Claude 能主动将重要信息写入持久存储，后续可主动检索 |
| **上下文裁剪** | 在发送给 Claude 前，智能地裁剪不相关的上下文 |
| **渐进式压缩** | 新对话保留细节 → 稍旧轻量总结 → 更早简短摘要 |

**关键原则**: 
- 三者协同，确保 Claude 始终获得最相关的上下文
- 原始数据完整保留在 Session (不丢失)

### seed-agent 当前实现

**AgentLoop 摘要机制**:

```python
# agent_loop.py
def _should_summarize(self) -> tuple[bool, int, bool]:
    # 单阈值触发: 75% 或 10 轮
    estimated_tokens = self._estimate_context_size()
    token_threshold = self.context_window * 0.75  # 单阈值
    is_round_limit_reached = self._conversation_rounds >= 10
    return (estimated_tokens > token_threshold or is_round_limit_reached)

def _apply_summary(self, summary: str, is_context_full: bool):
    # 二进制保留: 保留 2 或 4 条
    keep_count = 2 if is_context_full else 4
    preserved = self.history[-keep_count:]
    self.history = [{"role": "user", "content": f"[摘要]\n{summary}"}] + preserved
    # 问题: 历史被截断，无渐进分层
```

**问题**:
- ❌ 单阈值触发，无渐进分层
- ❌ 无智能裁剪 (不评估相关性)
- ❌ 历史被截断 (丢失数据)
- ❌ 无上下文相关性评估

---

## 设计方案

### 1. 渐进式上下文压缩

**三层压缩策略**:

```
┌─────────────────────────────────────────────────────────────┐
│                    对话历史                                   │
│                                                              │
│    [最新 5 轮] → 完整保留 (Full)                              │
│    [稍旧 10 轮] → 轻量总结 (Light Summary)                    │
│    [更早历史] → 简短摘要 (Abstract)                           │
│                                                              │
│    ↑ 渐进信息损失，不丢失原始数据 (Session 保留)               │
└─────────────────────────────────────────────────────────────┘
```

```python
class ProgressiveContextCompressor:
    """渐进式上下文压缩"""
    
    COMPRESSION_TIERS = {
        "tier_1": {
            "name": "recent_full",
            "threshold": 0.0,  # 最新部分
            "keep_count": 5,
            "method": "full",  # 完整保留
            "description": "最新 5 轮对话完整保留"
        },
        "tier_2": {
            "name": "medium_light",
            "threshold": 0.5,  # 50% 容量时
            "keep_count": 10,
            "method": "light_summary",
            "description": "稍旧 10 轮轻量总结"
        },
        "tier_3": {
            "name": "old_abstract",
            "threshold": 0.75,  # 75% 容量时
            "keep_count": None,  # 全部压缩
            "method": "abstract",
            "description": "更早历史简短摘要"
        },
    }
    
    def __init__(self, llm_gateway: LLMGateway):
        self._llm_gateway = llm_gateway
    
    def compress(self, session: SessionEventStream, context_window: int) -> list[dict]:
        """应用三层压缩
        
        Args:
            session: 事件流 (原始数据不丢失)
            context_window: 上下文窗口大小
        
        Returns:
            压缩后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._build_history_from_session(session)
        
        # 2. 计算当前容量
        current_usage = self._estimate_tokens(full_history)
        usage_ratio = current_usage / context_window
        
        # 3. 根据使用率决定压缩层级
        compressed = []
        
        if usage_ratio < 0.5:
            # Tier 1: 无压缩，保留全部
            compressed = full_history[-20:]  # 最多 20 条
        
        elif usage_ratio < 0.75:
            # Tier 1 + Tier 2: 保留最新 + 轻量总结
            compressed = self._apply_tier_1_and_2(full_history)
        
        else:
            # Tier 1 + Tier 2 + Tier 3: 完整三层
            compressed = self._apply_all_tiers(full_history)
        
        return compressed
    
    def _apply_tier_1_and_2(self, history: list[dict]) -> list[dict]:
        """应用 Tier 1 + Tier 2"""
        compressed = []
        
        # Tier 1: 最新 5 轮完整保留
        recent = history[-10:]  # 5 轮 ≈ 10 条消息
        compressed.extend(recent)
        
        # Tier 2: 稍旧 10 轮轻量总结
        medium = history[-30:-10]
        if medium:
            summary = await self._light_summarize(medium)
            compressed.append({
                "role": "system",
                "content": f"[中等对话摘要 - 轻量]\n{summary}"
            })
        
        return compressed
    
    def _apply_all_tiers(self, history: list[dict]) -> list[dict]:
        """应用全部三层"""
        compressed = []
        
        # Tier 1: 最新 5 轮完整保留
        recent = history[-10:]
        compressed.extend(recent)
        
        # Tier 2: 稍旧轻量总结
        medium = history[-30:-10]
        if medium:
            light_summary = await self._light_summarize(medium)
            compressed.append({
                "role": "system",
                "content": f"[中等对话摘要]\n{light_summary}"
            })
        
        # Tier 3: 更早简短摘要
        old = history[:-30]
        if old:
            abstract = await self._abstract_summarize(old)
            compressed.append({
                "role": "system",
                "content": f"[历史摘要 - 简短]\n{abstract}"
            })
        
        return compressed
    
    async def _light_summarize(self, messages: list[dict]) -> str:
        """轻量总结: 保留主要操作和结果"""
        prompt = f"""请对以下对话片段进行轻量总结，保留主要操作和结果:

{self._format_messages(messages)}

轻量总结格式:
- 主要操作: ...
- 关键结果: ...
- 重要发现: ...
"""
        response = await self._llm_gateway.chat_completion([{"role": "user", "content": prompt}])
        return response["choices"][0]["message"]["content"]
    
    async def _abstract_summarize(self, messages: list[dict]) -> str:
        """简短摘要: 仅保留核心结论"""
        prompt = f"""请用1-2句话总结以下对话片段的核心结论:

{self._format_messages(messages)}

格式: 核心结论是...
"""
        response = await self._llm_gateway.chat_completion([{"role": "user", "content": prompt}])
        return response["choices"][0]["message"]["content"]
```

### 2. 智能上下文裁剪

```python
class IntelligentContextPruner:
    """智能上下文裁剪"""
    
    def __init__(self, llm_gateway: LLMGateway):
        self._llm_gateway = llm_gateway
        self._entity_extractor = EntityExtractor()
    
    def prune_for_task(self, history: list[dict], current_task: str) -> list[dict]:
        """根据当前任务裁剪不相关上下文
        
        Args:
            history: 完整历史
            current_task: 当前任务描述
        
        Returns:
            裁剪后的历史 (保留高相关性)
        """
        # 1. 识别当前任务的关键实体
        entities = self._extract_entities(current_task)
        
        # 2. 计算每条历史消息的相关性分数
        relevance_scores = self._compute_relevance(history, entities)
        
        # 3. 保留高相关性消息
        pruned = []
        for msg, score in zip(history, relevance_scores):
            if score > RELEVANCE_THRESHOLD:
                pruned.append(msg)
        
        # 4. 添加裁剪说明
        if len(pruned) < len(history):
            pruned.append({
                "role": "system",
                "content": f"[裁剪说明: 已过滤 {len(history) - len(pruned)} 条低相关性历史，保留 {len(pruned)} 条]"
            })
        
        return pruned
    
    def _extract_entities(self, task: str) -> list[str]:
        """提取任务关键实体
        
        包括: 文件路径、函数名、类名、关键词
        """
        entities = []
        
        # 1. 文件路径 (如 "src/agent_loop.py")
        file_patterns = re.findall(r'[a-zA-Z_/]+\.[a-zA-Z]+', task)
        entities.extend(file_patterns)
        
        # 2. 函数/类名 (如 "AgentLoop", "_execute_tool")
        code_patterns = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', task)
        entities.extend(code_patterns)
        
        # 3. 关键词 (如 "重构", "优化", "bug")
        keywords = self._extract_keywords(task)
        entities.extend(keywords)
        
        return entities
    
    def _compute_relevance(self, history: list[dict], entities: list[str]) -> list[float]:
        """计算相关性分数
        
        Args:
            history: 消息历史
            entities: 关键实体列表
        
        Returns:
            每条消息的相关性分数 (0.0 - 1.0)
        """
        scores = []
        
        for msg in history:
            content = msg.get("content", "")
            if isinstance(content, str):
                # 计算实体匹配度
                entity_matches = sum(1 for e in entities if e.lower() in content.lower())
                entity_score = entity_matches / max(len(entities), 1)
                
                # 计算角色权重 (user/assistant 权重更高)
                role_weight = 1.0 if msg["role"] in ["user", "assistant"] else 0.5
                
                # 综合分数
                score = entity_score * role_weight
            else:
                score = 0.0
            
            scores.append(score)
        
        return scores
    
    async def _compute_semantic_relevance(self, history: list[dict], task: str) -> list[float]:
        """语义相关性计算 (使用 LLM)
        
        对于复杂任务，使用 LLM 评估相关性
        """
        scores = []
        
        for msg in history:
            prompt = f"""评估以下消息与当前任务的相关性:

任务: {task}

消息: {msg.get("content", "")}

相关性分数 (0-1): """
            
            response = await self._llm_gateway.chat_completion([{"role": "user", "content": prompt}])
            score_text = response["choices"][0]["message"]["content"]
            
            # 解析分数
            score = float(re.search(r'[\d.]+', score_text).group())
            scores.append(score)
        
        return scores
```

### 3. 集成到 Harness

```python
class HarnessWithContextEngineering:
    """带上下文工程的 Harness"""
    
    def __init__(
        self,
        claude: ClaudeClient,
        session: SessionEventStream,
        sandbox: Sandbox,
        context_window: int,
    ):
        self.claude = claude
        self.session = session  # 原始数据不丢失
        self.sandbox = sandbox
        self.context_window = context_window
        
        self._compressor = ProgressiveContextCompressor(claude.gateway)
        self._pruner = IntelligentContextPruner(claude.gateway)
    
    async def run_cycle(self, current_task: str = None) -> dict:
        """执行一轮对话循环"""
        # 1. 从 Session 构建完整历史
        full_history = self._build_history_from_session()
        
        # 2. 智能裁剪 (基于任务相关性)
        if current_task:
            pruned_history = self._pruner.prune_for_task(full_history, current_task)
        else:
            pruned_history = full_history
        
        # 3. 渐进式压缩
        compressed_context = self._compressor.compress(
            self.session,
            self.context_window
        )
        
        # 4. 调用 Claude 推理
        response = await self.claude.reason(compressed_context)
        
        # 5. 记录响应 (不修改原始历史)
        self.session.emit_event("llm_response", response)
        
        return {"response": response, "continue": response.get("tool_calls") is not None}
```

---

## 实施步骤

### Phase 1: 渐进式压缩实现 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 实现 ProgressiveContextCompressor 类 | 三层压缩逻辑正确 |
| 1.2 | 实现 light_summarize / abstract_summarize | LLM 摘要生成正确 |
| 1.3 | 集成到 AgentLoop/Harness | 压缩触发正确 |

### Phase 2: 智能裁剪实现 (5天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 实现 IntelligentContextPruner 类 | prune_for_task 正确 |
| 2.2 | 实现实体提取逻辑 | 文件/函数/关键词提取 |
| 2.3 | 实现相关性计算 | entity_matches 正确 |
| 2.4 | 实现语义相关性 (LLM) | _compute_semantic_relevance |
| 2.5 | 集成测试 | 裁剪效果验证 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **渐进式信息损失** | 60% → 75% → 90% 阈值分层处理 |
| **相关性过滤** | 裁剪不相关历史，保留关键信息 |
| **原始数据不丢失** | Session 保留完整历史 |
| **上下文利用率提升** | 避免无关信息浪费 Token |
| **长对话稳定性** | 渐进压缩防止突然截断 |

---

## 测试计划

```python
def test_progressive_compression():
    compressor = ProgressiveContextCompressor(gateway)
    
    # 创建 SessionEventStream
    session = SessionEventStream("test", Path("/tmp/test"))
    
    # 添加大量对话
    for i in range(100):
        session.emit_event("user_input", {"content": f"用户消息{i}"})
        session.emit_event("llm_response", {"content": f"助手回复{i}"})
    
    # 测试压缩
    compressed = compressor.compress(session, context_window=100000)
    
    # 验证分层
    assert len(compressed) < 200
    assert any("摘要" in msg.get("content", "") for msg in compressed)

def test_intelligent_pruning():
    pruner = IntelligentContextPruner(gateway)
    
    # 创建历史
    history = [
        {"role": "user", "content": "帮我重构 src/agent_loop.py"},
        {"role": "assistant", "content": "好的，开始重构 agent_loop.py"},
        {"role": "user", "content": "今天天气不错"},  # 无关消息
        {"role": "assistant", "content": "是的，天气很好"},  # 无关消息
        {"role": "user", "content": "AgentLoop 类的 _execute_tool 方法需要优化"},
    ]
    
    # 测试裁剪
    pruned = pruner.prune_for_task(history, "重构 agent_loop.py 的 _execute_tool 方法")
    
    # 验证裁剪效果
    assert len(pruned) < len(history)
    assert "裁剪说明" in [m.get("content", "") for m in pruned]
```

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流 (数据不丢失)
- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Harness 集成