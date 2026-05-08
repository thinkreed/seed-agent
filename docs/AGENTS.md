# Module Overview - Design Documentation

This directory contains design documents that capture architectural decisions, implementation plans, and technical specifications for the Seed Agent system. These documents serve as the authoritative reference for understanding why specific design choices were made.

---

## Available Documents

| Document | Description |
|----------|-------------|
| `wiki_knowledge_integration_analysis.md` | Wiki 知识落地分析：P0-P5 全部优化点实施记录 |
| `memory_graph_enhancement_design.md` | Memory Graph architecture for skill evolution and outcome tracking |
| `L4_SQLite_FTS5_Design.md` | L4 session storage migration from JSONL to SQLite+FTS5 |
| `long_cycle_loop_enhancement_design.md` | Ralph Loop architecture and implementation design |
| `ralph_loop.md` | Ralph Loop concept and motivation |
| `rate_limiting_system_design.md` | LLM request rate limiting system (Token Bucket + Queue + Persistence) |
| `request_queue_turn_ticket_design.md` | Request Queue TurnTicket 公平调度设计 |
| `harness/` | Harness 系列设计文档（6 个子文档） |

---

## Memory Graph Enhancement Design

**File:** `memory_graph_enhancement_design.md`

**Purpose:** Documents the Memory Graph architecture for skill evolution and outcome tracking, inspired by GEP (Gene Evolution Protocol).

**Key Sections:**
- Gene paper insights: "control density" vs "document completeness"
- Current Skill system limitations (no evolution feedback loop)
- gene_outcomes table design in L4 SQLite
- Selection algorithm: Laplace smoothing + confidence decay
- Ban threshold for low-value strategies
- Skill frontmatter enhancement (strategy, avoid, constraints)
- Integration points with AgentLoop, AutonomousExplorer, RalphLoop

**Core Mechanisms:**
1. **Outcome Tracking**: Every skill execution records (skill_name, signal_pattern, outcome)
2. **Evidence-Based Selection**: Historical success rates guide skill selection
3. **Confidence Decay**: Older outcomes carry less weight (30-day half-life)
4. **Ban Threshold**: Strategies with value < 0.18 and 2+ attempts are banned
5. **Gene-Style Control**: Frontmatter strategy/avoid fields as compact control signals

**Why Memory Graph:**
- Prevents repeated mistakes (banned strategies)
- Natural selection for successful strategies
- Quantifiable evolution metrics
- Token-efficient skill injection (Gene slice ~230 tokens)

---

## L4 SQLite+FTS5 Design

**File:** `L4_SQLite_FTS5_Design.md`

**Purpose:** Documents the migration from JSONL file-based session storage to SQLite+FTS5 database.

**Key Sections:**
- Current JSONL implementation limitations
- SQLite+FTS5 architecture with jieba Chinese tokenization
- Database schema design (session_messages, sessions_meta, FTS5 virtual table)
- Migration strategy and compatibility
- Performance benchmarks and PRAGMA optimizations
- API compatibility with existing memory tools

**Why SQLite+FTS5:**
- Efficient full-text search for Chinese content (jieba tokenization)
- Better query performance for history searches
- Atomic transactions for data integrity
- WAL mode for concurrent access

---

## Ralph Loop Enhancement Design

**File:** `long_cycle_loop_enhancement_design.md`

**Purpose:** Documents the Ralph Loop architecture for long-cycle deterministic task execution.

**Key Sections:**
- Problem analysis: context drift in long-running tasks
- 3-layer architecture: Verification Layer, Execution Layer, Safety Layer
- Completion promise mechanism
- Context reset strategy
- State persistence for crash recovery
- Safety limits (iterations and duration)
- Implementation details and code examples

**Core Mechanisms:**
1. **External Verification**: Completion driven by objective criteria (tests, markers, git)
2. **Fresh Context**: Periodic history reset prevents drift
3. **State Persistence**: Crash recovery via filesystem state
4. **Safety Limits**: Max iterations and duration protection

---

## Rate Limiting System Design

**File:** `rate_limiting_system_design.md`

**Purpose:** Documents the LLM request rate limiting system to prevent Provider API rate limit errors during concurrent subagent execution.

**Key Sections:**
- Problem analysis: Subagent parallel execution causing burst LLM requests
- 4-layer architecture: Rolling Window + Token Bucket + Semaphore + Queue
- Config-driven rate limits via `config.json`
- Two rate limit modes: rolling window (百炼) and fixed RPM (OpenAI)
- State persistence for crash recovery
- Request priority system (CRITICAL/HIGH/NORMAL/LOW)

**Core Mechanisms:**
1. **RollingWindowTracker**: 5-hour sliding window tracking (6000 requests limit)
2. **TokenBucket**: Burst smoothing at 0.33 req/sec
3. **Semaphore**: Concurrent request limit (max_concurrent=3)
4. **RequestQueue**: Async dispatch with priority and backpressure
5. **RateLimitSQLite**: Cross-process state persistence

**Why Rate Limiting:**
- Prevents Provider 429 errors during parallel subagent execution
- Precise rate control matching Provider specs (百炼: 6000/5h)
- Burst capacity for short-term spikes
- Queue for low-priority background tasks
- Crash recovery via state persistence

---

## Ralph Loop Concept

**File:** `ralph_loop.md`

**Purpose:** Explains the conceptual motivation and design philosophy behind Ralph Loop.

**Key Concepts:**
- The "Ralph" metaphor: rolling the boulder with persistence
- Deterministic vs self-judged completion
- External verification as objective truth
- Context freshness as drift prevention
- Long-cycle task patterns and use cases

---

## Document Usage Guidelines

### When to Read These Documents

- **Memory Graph Design**: Before modifying skill selection, outcome tracking, or frontmatter schema
- **L4 SQLite Design**: Before modifying session storage or adding search features
- **Ralph Loop Design**: Before implementing long-cycle tasks or modifying autonomous.py
- **Ralph Loop Concept**: To understand the design philosophy and motivation
- **Rate Limiting Design**: Before modifying LLM request handling, subagent execution, or adding new providers

### How These Documents Relate to Code

| Document | Related Code |
|----------|--------------|
| Memory Graph Design | `src/tools/skill_loader.py`, `src/tools/session_db.py`, `src/agent_loop.py` |
| L4 SQLite Design | `src/tools/session_db.py`, `src/tools/memory_tools.py` |
| Ralph Loop Design | `src/ralph_loop.py`, `src/autonomous.py`, `src/tools/ralph_tools.py` |
| Ralph Loop Concept | Architecture decision rationale |
| Rate Limiting Design | `src/client.py`, `src/rate_limiter.py`, `src/request_queue.py`, `src/rate_limit_db.py`, `src/subagent_manager.py` |

---

## Future Design Documents

Planned design documents to add:

| Planned Document | Purpose |
|------------------|---------|
| Scheduler Design | Task scheduling architecture and built-in tasks |

**Completed documents:**
- ✅ Memory Graph Enhancement Design (skill evolution and outcome tracking)
- ✅ L4 SQLite+FTS5 Design (session storage migration)
- ✅ Ralph Loop Enhancement Design (long-cycle task execution)
- ✅ Ralph Loop Concept (design philosophy)
- ✅ Subagent Design (in `subagents.md`)
- ✅ Rate Limiting System Design (LLM request rate control)
- ✅ Credential Security Design (Vault + Proxy architecture, see `harness/08_credential_security_design.md`)
- ✅ Wiki Knowledge Integration (P0-P5 全部完成，详见 `wiki_knowledge_integration_analysis.md`)

---

## Wiki Knowledge Integration (P4+P5 新功能)

详见 `wiki_knowledge_integration_analysis.md`，以下为 P4+P5 新增功能模块：

### Circuit Breaker 自动切换 (P4)

**实现位置**: `src/client/_circuit_breaker.py`

**功能**: Provider 熔断器，连续失败自动切换备用 Provider，自动恢复探测。

**核心机制**:
- 状态机: Closed → Open (连续失败达阈值) → HalfOpen (冷却结束) → Closed (探测成功)
- 独立 Provider 熔断配置（借鉴 worldmonitor "每个数据域独立熔断")
- 并发安全：asyncio.Lock 保护状态变更

### Orphan Reaper 孤儿回收 (P4)

**实现位置**: `src/subagent_manager_core/_orphan_reaper.py`

**功能**: 定期扫描和回收超时的孤儿 Subagent 进程。

**核心机制**:
- 每 30 秒扫描活跃进程
- 两阶段终止: SIGTERM → 等待 5s → SIGKILL
- 进程注册/注销 API

### Stampede Protection 缓存击穿保护 (P4)

**实现位置**: `src/request_queue_core/_stampede.py`

**功能**: 并发缓存击穿保护，单个请求实际调用，其他等待共享结果。

**核心机制**:
- `get_or_refresh(key, refresh_fn)` - 获取或刷新
- 防重复请求：`inflight` Map 共享 Task
- 失效策略：`invalidate(key)` 触发重新刷新

### 复杂度评分路由 (P4)

**实现位置**: `src/client/_complexity_scorer.py`

**功能**: 23 维度复杂度评分 → 四级 Tier 路由（simple/standard/complex/reasoning）。

**23 维度**:
- 代码复杂度（5维）：file_count, line_count, function_count, nesting_depth, dependency_count
- 任务复杂度（6维）：step_count, decision_points, parallel_tasks, verification_needed, documentation_needed, test_needed
- 上下文复杂度（4维）：message_count, token_count, file_references, history_length
- 工具复杂度（4维）：tool_count, tool_types, cross_domain_calls, permission_level
- 知识复杂度（4维）：domain_count, concept_count, reasoning_depth, uncertainty_level

### Specificity 检测 (P4)

**实现位置**: `src/client/_specificity_detector.py`

**功能**: 任务类型自动检测，路由到专用模型。

**三层路由优先级**: Header Tiers → Specificity → Complexity

### Merkle DAG 增量索引 (P5)

**实现位置**: `src/core/_merkle_dag.py`

**功能**: O(1) 无变更检测 + O(k) 增量更新。

**核心机制**:
- Merkle 哈希树：文件变更检测
- 增量构建：只更新变更节点
- 快照管理：历史版本追踪

### DataHub Pub/Sub (P5)

**实现位置**: `src/core/_datahub.py`

**功能**: Topic 发布订阅 + 请求去重。

**核心机制**:
- `publish(topic, data)` - 发布数据
- `subscribe(topic, handler)` -订阅处理
- TopicPolicy 策略：TTL/Rate Limit/Refresh

### QueryInvalidator 失效策略 (P5)

**实现位置**: `src/core/_query_invalidator.py`

**功能**: 失效策略 + 缓存管理 + 乐观更新回滚。

**核心机制**:
- `invalidate(query_pattern)` - 失效匹配查询
- `with_optimistic_update(query, update, rollback)` - 乐观更新回滚 |