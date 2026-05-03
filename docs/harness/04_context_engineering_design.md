# 优化点 04: 渐进式上下文压缩 + 智能裁剪

> **版本**: v2.0 (已实现)
> **创建日期**: 2026-05-03
> **实现日期**: 2026-05-03
> **优先级**: 中
> **依赖**: 01_session_event_stream_design
> **参考来源**: Harness Engineering "上下文工程"
> **实现状态**: ✅ 已完成

---

## 实现概览

本优化点已完成实现，核心模块位于 `src/context_engineering.py`，包含三个主要组件：

| 组件 | 类名 | 功能 |
|------|------|------|
| **渐进式压缩** | `ProgressiveContextCompressor` | 三层压缩策略 |
| **智能裁剪** | `IntelligentContextPruner` | 任务相关性过滤 |
| **集成管理器** | `ContextEngineering` | 协调压缩与裁剪 |

**集成点**:
- `AgentLoop` - 初始化 `ContextEngineering` 实例
- `Harness` - 使用 `_build_context_from_session()` 应用优化

---

## 问题分析（已解决）

### 原有问题

| 问题 | 状态 |
|------|------|
| ❌ 单阈值触发，无渐进分层 | ✅ 已解决 - 三层压缩 |
| ❌ 无智能裁剪 (不评估相关性) | ✅ 已解决 - 实体提取 + 相关性计算 |
| ❌ 历史被截断 (丢失数据) | ✅ 已解决 - Session 只追加 |
| ❌ 无上下文相关性评估 | ✅ 已解决 - 实体匹配 + 语义评估 |

---

## 实现设计

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

**实现代码** (`src/context_engineering.py`):

```python
class ProgressiveContextCompressor:
    """渐进式上下文压缩"""

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str,
        config: CompressionConfig | None = None
    ):
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or CompressionConfig()

    def compress(
        self,
        session: SessionEventStream,
        context_window: int,
        system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """应用三层压缩（同步版本）

        Args:
            session: 事件流（原始数据不丢失）
            context_window: 上下文窗口大小
            system_prompt: 系统提示

        Returns:
            压缩后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._build_history_from_session(session, system_prompt)

        # 2. 计算当前容量使用率
        current_tokens = self._estimate_tokens(full_history)
        usage_ratio = current_tokens / context_window

        # 3. 根据使用率决定压缩层级
        if usage_ratio < 0.5:
            compressed = self._apply_tier_1_only(full_history)
        elif usage_ratio < 0.75:
            compressed = self._apply_tier_1_and_2(full_history)
        else:
            compressed = self._apply_all_tiers(full_history)

        return compressed

    async def compress_async(...) -> list[dict[str, Any]]:
        """异步版本 - 使用 LLM 生成摘要"""
        ...
```

**配置数据类**:

```python
@dataclass
class TierConfig:
    """层级配置"""
    name: str
    threshold: float          # 容量阈值触发点
    keep_rounds: int          # 保留轮数 (一轮 ≈ 2 条消息)
    method: CompressionTier
    description: str

@dataclass
class CompressionConfig:
    """压缩配置"""
    tiers: dict[CompressionTier, TierConfig] = {
        CompressionTier.TIER_1_FULL: TierConfig(
            name="recent_full",
            threshold=0.0,
            keep_rounds=5,
            method=CompressionTier.TIER_1_FULL,
            description="最新 5 轮对话完整保留"
        ),
        CompressionTier.TIER_2_LIGHT: TierConfig(
            name="medium_light",
            threshold=0.5,
            keep_rounds=10,
            method=CompressionTier.TIER_2_LIGHT,
            description="稍旧 10 轮轻量总结"
        ),
        CompressionTier.TIER_3_ABSTRACT: TierConfig(
            name="old_abstract",
            threshold=0.75,
            keep_rounds=0,  # 全部压缩
            method=CompressionTier.TIER_3_ABSTRACT,
            description="更早历史简短摘要"
        ),
    }
    token_per_char: float = 0.5
    max_context_messages: int = 50
```

### 2. 智能上下文裁剪

**实现代码**:

```python
class IntelligentContextPruner:
    """智能上下文裁剪"""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        model_id: str | None = None,
        config: PruningConfig | None = None
    ):
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or PruningConfig()

    def prune_for_task(
        self,
        history: list[dict[str, Any]],
        current_task: str
    ) -> list[dict[str, Any]]:
        """根据当前任务裁剪不相关上下文

        Args:
            history: 完整历史
            current_task: 当前任务描述

        Returns:
            裁剪后的历史（保留高相关性）
        """
        # 1. 系统消息和摘要消息总是保留
        always_preserve = [
            m for m in history
            if m["role"] == "system" or "摘要" in m.get("content", "")
        ]

        # 2. 提取任务关键实体
        entities = self._extract_entities(current_task)

        # 3. 计算相关性分数
        relevance_scores = self._compute_relevance(prunable, entities)

        # 4. 保留高相关性消息
        pruned = [
            m for m, s in zip(prunable, relevance_scores)
            if s > self._config.relevance_threshold
        ]

        # 5. 最小保留保护
        if len(pruned) < self._config.min_preserve_count:
            # 按分数排序，保留最高的
            ...

        # 6. 添加裁剪说明
        ...

        return result

    def _extract_entities(self, task: str) -> list[str]:
        """提取任务关键实体：文件路径、函数名、类名、关键词"""
        entities: list[str] = []

        # 1. 文件路径 (如 "src/agent_loop.py")
        file_patterns = re.findall(r'[a-zA-Z_./]+\.[a-zA-Z]+', task)
        entities.extend(file_patterns)

        # 2. 函数/类名 (CamelCase 和 snake_case)
        code_patterns = re.findall(r'[A-Z][a-zA-Z0-9]*|[a-z_][a-z0-9_]*', task)
        entities.extend(code_patterns)

        # 3. 关键词 (技术词汇)
        keywords = self._extract_keywords(task)
        entities.extend(keywords)

        return list(set(entities))

    def _compute_relevance(
        self,
        history: list[dict[str, Any]],
        entities: list[str]
    ) -> list[float]:
        """计算相关性分数（实体匹配 + 角色权重）"""
        scores: list[float] = []

        for msg in history:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # 实体匹配度
            entity_matches = sum(
                1 for e in entities
                if e.lower() in content.lower()
            )
            entity_score = entity_matches / max(len(entities), 1)

            # 角色权重
            role_weight = self._config.role_weights.get(role, 0.5)

            # 综合分数
            score = entity_score * role_weight
            scores.append(score)

        return scores
```

### 3. 集成管理器

```python
class ContextEngineering:
    """上下文工程集成管理器

    协调渐进式压缩和智能裁剪：
    - 先裁剪（基于任务相关性）
    - 后压缩（基于容量使用率）
    """

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str,
        compression_config: CompressionConfig | None = None,
        pruning_config: PruningConfig | None = None
    ):
        self._gateway = gateway
        self._model_id = model_id

        self._compressor = ProgressiveContextCompressor(gateway, model_id, compression_config)
        self._pruner = IntelligentContextPruner(gateway, model_id, pruning_config)

    def build_optimized_context(
        self,
        session: SessionEventStream,
        context_window: int,
        current_task: str | None = None,
        system_prompt: str | None = None,
        enable_pruning: bool = True
    ) -> list[dict[str, Any]]:
        """构建优化后的上下文（同步版本）

        流程：
        1. 从 Session 构建完整历史
        2. 智能裁剪（可选，基于任务相关性）
        3. 渐进式压缩（基于容量使用率）
        """
        # 1. 构建历史
        full_history = self._compressor._build_history_from_session(session, system_prompt)

        # 2. 智能裁剪
        if enable_pruning and current_task:
            pruned_history = self._pruner.prune_for_task(full_history, current_task)
        else:
            pruned_history = full_history

        # 3. 渐进式压缩
        compressed = self._apply_compression_to_pruned(pruned_history, context_window)

        return compressed

    async def build_optimized_context_async(...) -> list[dict[str, Any]]:
        """异步版本 - 支持 LLM 摘要和语义裁剪"""
        ...
```

### 4. Harness 集成

```python
class Harness:
    """Harness 控制器 - 支持上下文工程"""

    def __init__(
        self,
        llm_client: LLMClient,
        session: SessionEventStream,
        sandbox: Sandbox,
        max_iterations: int = MAX_ITERATIONS,
        system_prompt: str | None = None,
        context_engineering: ContextEngineering | None = None,
        context_window: int = 100000,
        enable_pruning: bool = True
    ):
        self._context_engineering = context_engineering
        self._context_window = context_window
        self._enable_pruning = enable_pruning
        self._current_task: str | None = None
        ...

    def _build_context_from_session(
        self,
        current_task: str | None = None
    ) -> list[dict[str, Any]]:
        """从 Session 构建优化上下文"""
        if self._context_engineering:
            return self._context_engineering.build_optimized_context(
                session=self.session,
                context_window=self._context_window,
                current_task=current_task or self._current_task,
                system_prompt=self.system_prompt,
                enable_pruning=self._enable_pruning
            )

        # 无上下文工程时，使用 Session 原生方法
        return self.session.build_context_for_llm(system_prompt=self.system_prompt)

    def set_current_task(self, task: str) -> None:
        """设置当前任务（用于智能裁剪）"""
        self._current_task = task
```

### 5. AgentLoop 集成

```python
class AgentLoop:
    """Agent 主循环 - 集成上下文工程"""

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 30,
        summary_interval: int = 10,
        session_id: str | None = None,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        compression_config: CompressionConfig | None = None,
        pruning_config: PruningConfig | None = None,
        enable_pruning: bool = True,
    ):
        self._compression_config = compression_config
        self._pruning_config = pruning_config
        self._enable_pruning = enable_pruning
        ...

    def _setup_context_engineering(self) -> None:
        """初始化上下文工程"""
        self._context_engineering = ContextEngineering(
            gateway=self.gateway,
            model_id=self.model_id,
            compression_config=self._compression_config,
            pruning_config=self._pruning_config
        )

        # 将 ContextEngineering 实例传递给 Harness
        self.harness._context_engineering = self._context_engineering
```

---

## 实施步骤（已完成）

### Phase 1: 渐进式压缩实现 ✅

| 步骤 | 任务 | 状态 |
|------|------|------|
| 1.1 | 实现 `ProgressiveContextCompressor` 类 | ✅ 已完成 |
| 1.2 | 实现 `light_summarize` / `abstract_summarize` | ✅ 已完成 |
| 1.3 | 集成到 AgentLoop/Harness | ✅ 已完成 |

### Phase 2: 智能裁剪实现 ✅

| 步骤 | 任务 | 状态 |
|------|------|------|
| 2.1 | 实现 `IntelligentContextPruner` 类 | ✅ 已完成 |
| 2.2 | 实现实体提取逻辑 | ✅ 已完成 |
| 2.3 | 实现相关性计算 | ✅ 已完成 |
| 2.4 | 实现语义相关性 (LLM) | ✅ 已完成 |
| 2.5 | 集成测试 | ✅ 已完成 |

---

## 预期收益（已验证）

| 收益 | 描述 | 验证状态 |
|------|------|----------|
| **渐进式信息损失** | 50% → 75% 阈值分层处理 | ✅ 已验证 |
| **相关性过滤** | 裁剪不相关历史，保留关键信息 | ✅ 已验证 |
| **原始数据不丢失** | Session 保留完整历史 | ✅ 已验证 |
| **上下文利用率提升** | 避免无关信息浪费 Token | ✅ 已验证 |
| **长对话稳定性** | 渐进压缩防止突然截断 | ✅ 已验证 |

---

## 测试计划（已实现）

测试文件：`tests/test_context_engineering.py`

**核心测试用例**:

| 测试 | 描述 |
|------|------|
| `test_compress_tier_1_only` | 低使用率：仅 Tier 1 |
| `test_compress_tier_1_and_2` | 中使用率：Tier 1 + 2 |
| `test_compress_all_tiers` | 高使用率：完整三层 |
| `test_extract_entities_file_paths` | 文件路径实体提取 |
| `test_extract_entities_code_names` | 代码名称实体提取 |
| `test_compute_relevance` | 相关性分数计算 |
| `test_prune_for_task` | 任务相关裁剪 |
| `test_original_data_preserved` | 原始数据保留验证 |

---

## 相关文档

- [01_session_event_stream_design.md](01_session_event_stream_design.md) - Session 事件流 (数据不丢失)
- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Harness 集成
- [src/AGENTS.md](../src/AGENTS.md) - 核心引擎文档
- [src/context_engineering.py](../src/context_engineering.py) - 实现代码