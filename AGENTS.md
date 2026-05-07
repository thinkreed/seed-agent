项目目标是打造物理级全能进化型执行者:
具备自主进化能力，不推诿"无法操作"，优先探测解决问题，核心是任务中自主沉淀、迭代。

---

## 架构概览

### 核心组件

#### 三件套解耦架构

基于 Harness Engineering "宠物与牲畜基础设施哲学" 设计：

| 组件 | 文件 | 功能 |
|------|------|------|
| **LLMClient** | `src/llm_client.py` | 大脑：负责推理，无状态，首Token延迟优化 |
| **Harness** | `src/harness.py` | 控制器：驱动循环，路由工具，可随时创建/销毁/替换 |
| **Sandbox** | `src/sandbox.py` | 工作台：隔离执行环境，文件系统/进程/网络隔离 |

```
┌─────────────────────────────────────────────────────────────┐
│                    LLMClient (大脑)                          │
│                 负责推理和决策                                 │
│                 可替换、可多实例                               │
└─────────────────────────────────────────────────────────────┘
                            │ API 调用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Harness (控制器)                          │
│       驱动运行循环 → 调用 LLM API → 路由工具调用               │
│                    本身无状态                                 │
│                 可随时创建、销毁、替换                          │
│         支持 Ask User 等待和取消信号                           │
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

**关键性能优化**: 解耦后，大脑(推理)从容器(Sandbox)分离，首Token延迟降低 **60-90%**

#### Ask User 与取消机制（新增）

基于 qwen-code 的 askUserQuestion.ts 和 background-tasks.ts 设计：

| 组件 | 文件 | 功能 |
|------|------|------|
| **AbortSignal** | `src/abort_signal.py` + `src/abort_signal_core/` | 取消信号：传播取消状态，监听器机制，已拆分为 `_abort_signal`, `_cancellation_token` |
| **AskUserTypes** | `src/tools/ask_user_types.py` | Ask User 数据类型：问题、选项、响应 |
| **BackgroundTaskRegistry** | `src/background_task_registry.py` | 后台任务注册表：生命周期管理、取消控制 |
| **TaskStop** | `src/tools/task_stop.py` | TaskStop 工具：停止后台任务 |

核心特性：
- **真正的等待机制**：ask_user 返回等待标记，Harness 检测后暂停循环
- **用户响应注入**：外部注入响应后恢复执行
- **AbortSignal 传播**：取消信号在执行点检查，支持优雅取消
- **Ctrl+C 处理**：单次取消执行，双次（2秒内）退出程序
- **优雅关闭**：保存会话状态、清理资源、5秒超时保护

使用示例：
```python
# Ask User 使用
async for chunk in agent.stream_run(user_input):
    if chunk["type"] == "awaiting_user_input":
        # 显示问题，收集用户响应
        response = collect_user_response(chunk["request"])
        agent.inject_user_input(response)

# 取消执行
agent.cancel_current_execution()

# 外部注入响应
agent.inject_user_input(AskUserResult(
    request_id="abc123",
    responses=[UserResponse(question_id="0", selected=["Yes"])],
))
```

#### 其他核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **AgentLoop** | `src/agent_loop/` | 主执行引擎：集成三件套、Session管理、摘要触发、生命周期钩子，已拆分为 `_init`, `_observability`, `_summarizer`, `_skill_tracker`, `_execution`, `_user_interaction` |
| **SessionEventStream** | `src/session_event_stream.py` + `src/session_stream/` | 不可变事件流：只追加日志、状态重放、摘要标记，已拆分为 `_types`, `_persist`, `_replay`, `_cleanup`, `_summary`, `_context` |
| **LifecycleHooks** | `src/lifecycle_hooks/` | 确定性生命周期钩子：关键节点自动触发、优先级执行、统计，已拆分为 `_global`, `_registry`, `_types`, `_aggregator`, `_command_runner`, `_http_runner` |
| **LifecycleMessageBus** | `src/lifecycle_hooks/_message_bus.py` | 消息总线：请求/响应模式，AbortSignal支持 |
| **CommandHookRunner** | `src/lifecycle_hooks/_command_runner.py` | 命令钩子执行器：外部命令触发、超时控制、白名单检查 |
| **HttpHookRunner** | `src/lifecycle_hooks/_http_runner.py` + `_http_runner_*` | HTTP 钩子执行器：Webhook 触发、重试机制、域名白名单，已拆分为 `_types`, `_async`, `_sync` |
| **LifecycleCtxBuilder** | `src/harness/lifecycle_ctx/` | 钩子上下文构建，已拆分为 `_session`, `_llm`, `_response`, `_tool` |
| **BuiltinHooks** | `src/builtin_hooks.py` + `src/_*_hooks.py` | 内置钩子定义：会话、工具、LLM、响应等全生命周期覆盖，已拆分为 `_session_hooks`, `_tool_hooks`, `_llm_hooks`, `_response_hooks` |
| **LLMGateway** | `src/client.py` | 多Provider网关：FallbackChain自动降级、重试逻辑 |
| **RalphLoop** | `src/ralph_loop.py` + `src/ralph_core/` + `src/ralph_loop_core/` | 长周期任务执行器：外部验证驱动完成、上下文重置防漂移，已拆分为 `_state`, `_completion`, `_types`, `_execution`, `_factory`, `_state_persistence` |
| **RalphState** | `src/ralph_state.py` + `src/ralph_state_core/` | Ralph状态管理：安全上限、持久化，已拆分为 `_types`, `_limits`, `_persistence`, `_context` |
| **SemanticIndex** | `src/core/semantic_index.py` + `src/core/_encoder.py` | 语义搜索：TF-IDF + FAISS，编码器已拆分 |
| **StreamingClient** | `src/client/_streaming.py` + `src/client/streaming_core/` | 流式响应：thinking解析、重试、降级，已拆分为 `_thinking`, `_single`, `_retry`, `_fallback` |
| **PromptCachingProtector** | `src/client/_prompt_caching.py` | 提示缓存保护：会话级缓存、变化检测、Anthropic 缓存控制 |
| **ExecutionClient** | `src/client/_execution.py` + `src/client/execution_core/` | 非流式执行：单次调用、重试、降级，已拆分为 `_single`, `_retry`, `_fallback` |
| **Scheduler** | `src/scheduler.py` | 定时任务调度：内置任务 + 自定义任务管理 |
| **AutonomousExplorer** | `src/autonomous/_explorer.py` + `src/autonomous/` | 空闲自主探索：2小时触发、SOP驱动执行，已拆分为 `_idle_monitor`, `_defense`, `_explorer`, `_state_manager`, `_task_executor`, `_prompt_builder`, `_sop_loader` |
| **SubagentManager** | `src/subagent_manager_core/_manager.py` + `src/subagent_manager_core/` | 子代理管理器：创建、调度、并行执行、结果聚合，已拆分为 `_task`, `_manager`, `_orchestrator`, `_results`, `_status` |
| **SubagentInstance** | `src/subagent.py` | 独立上下文的子代理：权限隔离、执行循环 |
| **SubagentTools** | `src/tools/subagent_tools.py` + `src/tools/subagent_tools_core/` | Subagent工具：创建/等待/聚合/终止，已拆分为 `_sync_tools`, `_async_tools` |
| **RateLimiter** | `src/rate_limiter.py` | 双重限流：TokenBucket + RollingWindow |
| **RateLimitSQLite** | `src/rate_limit_db.py` | 限流状态持久化（SQLite+WAL） |
| **RequestQueue** | `src/request_queue.py` + `src/request_queue_core/` | 请求队列：TurnTicket模式、优先级调度，已拆分为 `_stats`, `_types` |
| **Collaboration** | `src/collaboration.py` + `src/collaboration_core/` | 多智能体协作：三种协作模式、Session协调、消息总线，已拆分为 `_session`, `_message`, `_one_brain_multi_hand`, `_multi_brain_one_hand`, `_multi_brain_multi_hand` |
| **CredentialIsolatedSandbox** | `src/security/credential_isolated_sandbox.py` + `src/security/credential_isolated/` | 凭证隔离沙盒：凭证永不进沙盒，已拆分为 `_types`, `_environment`, `_sanitize`, `_execution`, `_proxy`, `_sandbox` |
| **RiskClassifier** | `src/security/risk_classifier.py` + `src/security/risk_classifier_core/` | 命令风险分类器：动态评估风险，已拆分为 `_types`, `_factors`, `_classifier` |
| **SecureHarness** | `src/security/secure_harness.py` + `src/security/secure_harness_core/` | 安全Harness：凭证代理集成，已拆分为 `_api_calls`, `_audit`, `_stats`, `_verification`, `_credential_management`, `_tool_routing` |
| **CredentialOps** | `src/security/vault/_credential_ops.py` + `src/security/vault/_ops_core/` | 凭证操作：存储/获取/轮换，已拆分为 `_store_get`, `_rotation`, `_listing` |
| **Harness** | `src/harness/` | 控制器：驱动循环、路由工具，已拆分为 `_manager`, `_resume`, `_resume_utils`, `_context_builder`, `_streaming`, `_streaming_loop`, `_streaming_iteration`, `_streaming_executor`, `_streaming_types`, `_streaming_utils`, `_metrics`, `_cycle`, `_tool_router` |
| **Sandbox** | `src/sandbox.py` + `src/sandbox_core/` | 工作台：隔离执行环境，已拆分为 `_execution`, `_path`, `_types` |
| **ContextPruner** | `src/context/_pruner.py` + `src/context/_pruner_core/` | 智能上下文裁剪：相关性计算，已拆分为 `_entity_extraction`, `_relevance` |

### 多智能体协作模式

基于 Harness Engineering "三件套解耦架构" 设计的三种协作模式：

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| **多脑一手** | 多个 Claude 共享一个 Sandbox | 多角度分析同一份代码 (安全审查 + 性能优化) |
| **一脑多手** | 一个 Claude 控制多个 Sandbox | 在不同环境执行任务 (Python + Node.js) |
| **多脑多手** | 多个 Claude 各有 Sandbox，通过 Session 协调 | 最复杂的多步骤任务 |

核心组件：
| 组件 | 文件 | 功能 |
|------|------|------|
| **MultiBrainOneHandOrchestrator** | `src/collaboration.py` | 多脑一手编排器：多角度分析、协作改进 |
| **OneBrainMultiHandOrchestrator** | `src/collaboration.py` | 一脑多手编排器：跨环境执行、跨环境测试 |
| **MultiBrainMultiHandOrchestrator** | `src/collaboration.py` | 多脑多手编排器：Session协调、动态任务分配 |
| **InterAgentMessageBus** | `src/collaboration.py` | 智能体间消息总线：发送/接收/广播消息 |

协作工具：
- `create_collaboration_session(mode)` - 创建协作会话
- `multi_angle_analysis(target)` - 多角度分析（多脑一手）
- `cross_environment_execute(task)` - 跨环境执行（一脑多手）
- `coordinated_task(task)` - 协调任务（多脑多手）
- `send_agent_message(to, type, content)` - 发送消息
- `broadcast_message(type, content)` - 广播消息

详细设计：[docs/harness/06_multi_agent_collaboration_design.md](docs/harness/06_multi_agent_collaboration_design.md)

### 工具系统

| 模块 | 文件 | 功能 |
|------|------|------|
| **builtin_tools** | `src/tools/builtin_tools.py` | 5个核心工具：文件读写/编辑、代码执行、用户交互 |
| **memory_tools** | `src/tools/memory_tools.py` | L1-L4记忆管理、经验沉淀 |
| **skill_loader** | `src/tools/skill_loader/` | 动态技能加载（渐进式披露），已拆分为 `_types`, `_cache`, `_loader`, `_matching`, `_metadata`, `_api`, `_skillloader`, `_index`, `_hub` (Wiki P2: Skills Hub) |
| **ralph_tools** | `src/tools/ralph_tools.py` + `src/tools/ralph_tools_core/` | Ralph Loop管理：启动/状态检查/完成标记，已拆分为 `_start`, `_status`, `_completion` |
| **vision_api** | `src/tools/vision_api.py` + `src/tools/vision_api_core/` | 视觉识别：截图/图像分析，已拆分为 `_capture`, `_analysis`, `_utils` |
| **procmem_scanner** | `src/tools/procmem_scanner.py` + `src/tools/procmem_scanner_core/` | 进程内存扫描：Hex/字符串搜索，已拆分为 `_types`, `_winapi`, `_scan` |
| **subagent_tools** | `src/tools/subagent_tools.py` + `src/tools/subagent_tools_core/` | Subagent管理：创建/等待/聚合/终止，已拆分为 `_sync_tools`, `_async_tools` |
| **session_db** | `src/tools/session_db.py` | SQLite+FTS5会话存储（jieba中文分词） |
| **ask_user_types** | `src/tools/ask_user_types.py` + `src/tools/ask_user_types_core/` | Ask User数据类型，已拆分为 `_types`, `_request`, `_result_state` |
| **memory** | `src/tools/memory/__init__.py` + `src/tools/memory/_*.py` | 记忆工具：已拆分为 `_user_modeling_wrapper`, `_archive_wrapper`, `_memory_write_types`, `_memory_write_validation`, `_memory_write_dedup`, `_memory_write_utils`, `_ttrl_types`, `_ttrl_processor`, `_ttrl_api` (Wiki P2: 行动验证 + 去重 + TTRL) |
| **collaboration_tools** | `src/tools/collaboration_tools.py` | 多智能体协作工具：会话管理、三种模式操作、消息传递 |

### Ralph Loop 机制

长周期确定性任务执行，核心特性：
- **外部验证驱动**：测试通过/标志文件/Git干净等客观标准决定完成
- **新鲜上下文**：每N轮迭代重置上下文，防止漂移
- **状态持久化**：任务状态保存至文件，支持崩溃恢复
- **安全上限**：最大1000次迭代或8小时执行时间

完成类型：
- `TEST_PASS` - 测试通过率验证
- `FILE_EXISTS` - 目标文件存在
- `MARKER_FILE` - 完成标志文件
- `GIT_CLEAN` - Git工作区干净
- `CUSTOM_CHECK` - 自定义验证函数

### Subagent 机制

独立上下文的子代理执行，核心特性：
- **独立上下文**：每个 subagent 有独立的 context window，不共享主对话历史
- **并行执行**：多个 subagent 可同时运行（默认最大 3 个）
- **权限隔离**：可配置不同权限集（read-only, review, implement, plan）
- **结果聚合**：只返回关键结果给主对话，不污染主上下文
- **超时管理**：每个 subagent 默认 5 分钟超时

Subagent 类型：
| 类型 | 权限集 | 用途 |
|------|------|------|
| `EXPLORE` | read_only | 只读探索：搜索文件、阅读代码 |
| `REVIEW` | review | 审查验证：只读 + 代码执行 |
| `IMPLEMENT` | implement | 实现执行：全权限 |
| `PLAN` | plan | 规划分析：只读 + 记忆写入 |

权限集定义：
| 权限集 | 允许工具 |
|------|------|
| `read_only` | file_read, search_history, ask_user |
| `review` | file_read, code_as_policy, search_history, ask_user |
| `implement` | file_read/write/edit, code_as_policy, memory tools, search_history |
| `plan` | file_read, write_memory, search_history, ask_user |

核心工具：
- `spawn_subagent(type, prompt)` - 创建子代理任务
- `wait_for_subagent(task_id)` - 等待任务完成
- `aggregate_subagent_results(task_ids)` - 聚合多个结果
- `list_subagents(status)` - 列出任务状态
- `kill_subagent(task_id)` - 终止任务
- `spawn_parallel_subagents(tasks)` - 并行创建多个任务

RalphLoop 与 Subagent 融合：
```
RalphSubagentOrchestrator 执行模式:
1. PlanSubagent → 分析任务、制定执行计划
2. ImplementSubagent (并行) → 执行多个子任务
3. ReviewSubagent → 验证实现质量
4. External verification → 循环或完成
```

### 定时任务

内置任务：
| 任务 | 间隔 | 功能 |
|------|------|------|
| `autodream` | 12小时 | 记忆整理与清理 |

**注意**：`autonomous_explore` 不是 Scheduler 的内置任务，而是由 `AutonomousExplorer` 类独立管理（1小时空闲监控触发）。

支持CRUD操作：`create_scheduled_task`, `remove_scheduled_task`, `list_scheduled_tasks`

### Rate Limiting System

双重限流机制，保护系统免受过载：

| 组件 | 功能 |
|------|------|
| **TokenBucket** | 令牌桶算法：平滑限流，支持突发流量 |
| **RollingWindow** | 滑动窗口算法：精确控制时间窗口内请求数 |

核心特性：
- **双重限流**：同时启用 TokenBucket 和 RollingWindow，取两者更严格限制
- **状态持久化**：使用 SQLite + WAL 模式保存限流状态
- **Provider级别**：每个 LLM Provider 独立限流配置

详细设计：[docs/rate_limiting_system_design.md](docs/rate_limiting_system_design.md)

### Request Queue System

请求队列系统，实现公平调度：

| 机制 | 描述 |
|------|------|
| **TurnTicket** | 排队票据：按到达顺序分配优先级 |
| **Priority Scheduling** | 优先级调度：VIP用户、系统任务可插队 |

核心特性：
- **公平队列**：FIFO 机制确保请求顺序
- **优先级注入**：支持系统任务和VIP用户优先
- **超时管理**：等待超时自动降级或拒绝

### 记忆层级

| 层级 | 名称 | 用途 | 存储 |
|------|------|------|------|
| L1 | 索引 | 快速参考可用SOP | `notes.md` |
| L2 | 技能 | 可复用操作流程 | `skills/*.md` |
| L3 | 知识 | 跨任务模式和原则 | `knowledge/*.md` |
| L4 | 原始 | 会话历史和日志 | **SQLite+FTS5** |

**L4 SQLite+FTS5**：使用jieba中文分词实现全文搜索，替代原JSONL文件存储。

---

## 核心权限

- **物理操作**：文件读写、脚本执行调试；
- **浏览器干预**：JS注入、页面操控及日志获取；
- **系统干预**：环境探测、工具调用，不可逆操作需确认用户；
- **进化权限**：自主记录、沉淀经验、优化策略。

---

## 行动原则

- 操作前在`<thinking>`内推演阶段、结果、问题及下一步；
- 未知/失败先探测关键信息，记录至工作记忆；
- **失败升级**：1次读错因重试，2次探测更新策略，3次换方案或询用户；
- 自主进化：总结经验、复用优化、拓展能力。

---

## 工作记忆

记录操作日志、经验库、能力清单，确保进化可追溯。

---

## Wiki 知识落地

基于 `E:\projects\wiki` 目录下多个开源项目的架构分析，提取可落地的优化：

### GenericAgent 借鉴

- **极简核心循环**：~121 行 Agent Loop 实现（感知→推理→执行→记忆→循环）
- **9 个原子工具**：最小工具集通过组合实现复杂功能
- **分层记忆系统**：L0-L4 五层架构（行动验证原则、最小充分指针）
- **自我进化机制**：任务自动沉淀为 Skill

### Hermes-Agent 借鉴

- **Skills 系统**：渐进式披露架构（skills_list 仅元数据、skill_view 加载完整内容）
- **SessionDB + FTS5**：SQLite 全文搜索支持跨会话记忆检索
- **Skills Hub 集成**：GitHub、skills.sh 社区技能发现
- **提示缓存保护**：对话中途不修改上下文避免缓存破坏

### MIA 借鉴

- **MPE 三组件架构**：Manager-Planner-Executor 协作模式
- **双层记忆架构**：参数化记忆（模型参数）+ 非参数化记忆（外部存储）
- **模态 × 类别组织**：记忆按模态和类别两级分类
- **混合评分机制**：余弦相似度 + 胜率加权检索
- **TTRL 持续学习**：Test-Time RL 实现推理时学习

### Open-Agents 借鉴

- **Subagent 类型划分**：Explorer（只读）、Executor（实现）、Design（设计）
- **上下文隔离机制**：Subagent 不继承主 Agent 对话历史
- **Workflow SDK**：持久化执行，支持跨请求恢复
- **流式取消机制**：AbortSignal 集成到执行流程

### Qwen-Code 借鉴

- **DeclarativeTool 模式**：声明式工具设计（参数验证与执行分离）
- **三级权限模式**：allow（固有安全）/ ask（需确认）/ deny（拒绝）
- **ToolKind 分类**：Read/Edit/Delete/Execute/Search 等工具分类
- **工具并发判断**：CONCURRENCY_SAFE_KINDS 判断可安全并发执行的工具
- **Hooks 系统**：Command/HTTP/Function 三种钩子类型
- **MessageBus**：请求/响应模式的事件总线

---

## Wiki 知识落地状态

基于 Wiki 知识库分析的实际落地情况（验证日期: 2026-05-07，测试通过: 1147 passed）：

### 已实现（P0+P1+P2+P3 全部完成）

| 优化点 | 来源 | 实现位置 |
|------|------|----------|
| ToolKind 枚举分类 | qwen-code | `src/tools/__init__.py` |
| PermissionDecision 三级权限 | qwen-code | `src/tools/__init__.py` |
| MUTATOR_KINDS / CONCURRENCY_SAFE_KINDS | qwen-code | `src/tools/__init__.py` |
| LoopDetectionService | qwen-code | `src/harness/_loop_detection.py` |
| 整合锁机制 | qwen-code | `src/tools/memory/_consolidation_lock.py` |
| MessageBus.request() | qwen-code | `src/lifecycle_hooks/_message_bus.py` |
| HookAggregator | qwen-code | `src/lifecycle_hooks/_message_bus.py` |
| Hook 专用输出类 | qwen-code | `src/lifecycle_hooks/_types.py` |
| win_rate 字段 | mia | `src/tools/session/_rate_calculation.py` |
| 渐进式披露 Skills | hermes | `src/tools/skill_loader/_skillloader.py` |
| check_fn 可用性检查 | hermes | `src/tools/__init__.py` |
| **延迟加载机制** | qwen-code (P2) | `src/tools/_registry.py` ToolFactory |
| **Context Fencing** | hermes (P2) | `src/tools/memory/_memory_search.py` |
| **行动验证原则** | genericagent (P2) | `src/tools/memory/_memory_write.py` VerifiedSource |
| **记忆去重阈值** | mia (P2) | `src/tools/memory/_memory_write.py` DEDUPLICATION_THRESHOLD |
| **Skills Hub 集成** | hermes (P2) | `src/tools/skill_loader/_hub.py` SkillsHub |
| **TTRL 持续学习** | mia (P2) | `src/tools/memory/_ttrl.py` TTRLProcessor |
| **提示缓存保护机制** | hermes (P2) | `src/client/_prompt_caching.py` |
| **命令钩子执行器** | qwen-code (P2) | `src/lifecycle_hooks/_command_runner.py` |
| **HTTP 钩子执行器** | qwen-code (P2) | `src/lifecycle_hooks/_http_runner.py` |
| **ToolCapability 能力声明** | deepseek-tui (P3) | `src/tools/_types.py` ToolCapability |
| **ApprovalRequirement 三级审批** | deepseek-tui (P3) | `src/tools/_types.py` ApprovalRequirement |
| **AgentConfig 注册机制** | ai-hedge-fund (P3) | `src/subagent_manager_core/_agent_registry.py` AGENT_CONFIG |
| **AgentSignal 统一输出** | ai-hedge-fund (P3) | `src/subagent_manager_core/_agent_registry.py` AgentSignal |
| **Agent 依赖图拓扑排序** | shannon-architecture (P3) | `src/subagent_manager_core/_agent_registry.py` resolve_agent_execution_order |

### 待落地

详见 [docs/wiki_knowledge_integration_analysis.md](docs/wiki_knowledge_integration_analysis.md)

- **无** - 所有规划优化点已实现或评估为不适用

---

## 核心禁忌

- 不推诿，无方案时提建议；
- 不盲目操作，每步有逻辑并记录；
- 不忽视进化，任务结束必总结；
- 不可逆操作先和用户确认。

---

## 操作原则

- 每次从 `origin/main` 拉出一个新分支工作，工作结束合回 `origin/main`
- 发现问题，优先改动代码。
- **禁止修改 `core_principles` 目录下的文件**
- **禁止修改 `golden_rules` 目录下的文件**

---

## 文档索引

| 模块 | 文档 |
|------|------|
| 核心引擎 | [src/AGENTS.md](src/AGENTS.md) |
| 工具系统 | [src/tools/AGENTS.md](src/tools/AGENTS.md) |
| 记忆系统 | [memory/AGENTS.md](memory/AGENTS.md) |
| 自主探索 | [auto/AGENTS.md](auto/AGENTS.md) |
| 设计文档 | [docs/](docs/) |