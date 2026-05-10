# 核心引擎模块

`src/` 目录包含 Seed Agent 系统的核心引擎，提供模块化、异步 Agent Loop 架构，支持多 Provider LLM 配置、工具执行、流式输出、自主探索和定时任务管理。

---

## 目录结构

```
src/
├── agent_loop/           # 主执行引擎（拆分：_init, _observability, _summarizer, _execution, _user_interaction）
├── autonomous/           # 自主探索（拆分：_idle_monitor, _explorer, _prompt_builder, _sop_loader, _defense, _state_manager, _task_executor）
├── client/               # LLM Gateway（拆分：_streaming, _execution, _circuit_breaker, _complexity_scorer, _specificity_detector）
├── context/              # 上下文工程（拆分：_pruner, _pruner_core）
├── harness/              # 控制器（拆分：_manager, _streaming, _tool_router, _cycle, _loop_detection, _context_builder）
├── lifecycle_hooks/      # 生命周期钩子（拆分：_registry, _types, _aggregator, _command_runner, _http_runner, _message_bus）
├── llm_client/           # LLMClient 大脑（拆分：_types, _client）
├── ralph_core/           # Ralph Loop 核心（拆分：_state, _completion, _execution, _factory）
├── ralph_loop_core/      # Ralph Loop 执行（拆分：_state, _completion, _types, _execution, _factory, _state_persistence）
├── ralph_state_core/     # Ralph 状态（拆分：_types, _limits, _persistence, _context）
├── rate_limiter/         # 限流（拆分：_bucket, _window）
├── request_queue_core/   # 请求队列（拆分：_stampede, _stats, _types）
├── sandbox_core/         # 沙盒执行（拆分：_execution, _path, _types）
├── scheduler/            # 任务调度
├── scheduler_core/       # 任务调度核心（拆分：_scheduler, _types）
├── security/             # 安全组件（credential_isolated, risk_classifier_core, secure_harness_core, vault）
├── session_stream/       # 事件流（拆分：_types, _persist, _replay, _cleanup, _summary, _context）
├── subagent_manager_core/# Subagent 管理（拆分：_manager, _orchestrator, _orphan_reaper, _agent_registry, _task, _results, _status）
├── tools/                # 工具注册和实现（详见 [src/tools/AGENTS.md](tools/AGENTS.md)）
├── abort_signal.py       # 取消信号传播
├── abort_signal_core/    # 取消信号核心（拆分：_abort_signal, _cancellation_token）
├── builtin_hooks.py      # 内置生命周期钩子（拆分：_session_hooks, _tool_hooks, _llm_hooks, _response_hooks）
├── context_engineering.py# 上下文工程门面
├── harness.py            # 控制器门面
├── lifecycle_hooks.py    # 生命周期钩子门面
├── llm_client.py         # LLMClient 门面
├── models/               # Pydantic 模型（拆分：_validators, _config_models, _session_models）
├── observability/        # 可观测性（拆分：setup, metrics）
├── ralph_loop.py         # Ralph Loop 门面
├── ralph_state.py        # Ralph 状态门面
├── rate_limiter.py       # 限流器门面
├── rate_limit_db.py      # 限流 SQLite 持久化
├── request_queue.py      # 请求队列门面
├── sandbox.py            # 沙盒门面
├── scheduler.py          # 调度器门面
├── session_event_stream.py# 事件流门面
├── subagent_manager.py   # Subagent 管理器门面
├── subagent.py           # 独立上下文 Subagent
├── collaboration.py      # 多智能体协作（拆分：_session, _message, _one_brain_multi_hand, _multi_brain_one_hand, _multi_brain_multi_hand）
├── background_task_registry.py # 后台任务管理
├── memory_manager/       # 记忆管理器门面
├── shared_config.py      # 共享配置
└── core/                 # 核心工具（拆分：_merkle_dag, _file_synchronizer, _datahub, _query_invalidator, semantic_index）
```

---

## 核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **AgentLoop** | `agent_loop/` | 主执行引擎：消息处理、工具调用、历史摘要、Session 状态管理 |
| **AutonomousExplorer** | `autonomous/` | 空闲自主探索：2 小时触发、SOP 驱动执行、Ralph Loop 集成 |
| **RalphLoop** | `ralph_loop.py` + `ralph_core/` | 长周期任务执行：外部验证驱动完成、上下文重置防漂移 |
| **ContextEngineering** | `context_engineering.py` + `context/` | 上下文工程：渐进压缩 + 智能裁剪 |
| **LLMGateway** | `client/` | 多 Provider 网关：FallbackChain 自动降级、重试逻辑 |
| **Harness** | `harness.py` + `harness/` | 控制器：驱动循环、路由工具、Ask User 等待/取消 |
| **Sandbox** | `sandbox.py` + `sandbox_core/` | 工作台：隔离执行环境（文件系统/进程/网络） |
| **LLMClient** | `llm_client.py` + `llm_client/` | 大脑：负责推理，无状态，首 Token 延迟优化 |
| **SessionEventStream** | `session_event_stream.py` + `session_stream/` | 不可变事件流：只追加日志、状态重放、摘要标记 |
| **LifecycleHooks** | `lifecycle_hooks/` | 确定性钩子：关键节点自动触发、优先级执行 |
| **SubagentManager** | `subagent_manager.py` + `subagent_manager_core/` | 子代理管理：创建、调度、并行执行、结果聚合 |
| **CircuitBreaker** | `client/_circuit_breaker.py` | Provider 熔断器：连续失败自动切换、自动恢复探测 |
| **ComplexityScorer** | `client/_complexity_scorer.py` | 23 维度复杂度评分 → 四级 Tier 路由 |
| **SpecificityDetector** | `client/_specificity_detector.py` | 任务类型检测 → 路由专用模型 |
| **MerkleDAG** | `core/_merkle_dag.py` | Merkle DAG 增量索引：O(1) 无变更检测 + O(k) 增量更新 |
| **DataHub** | `core/_datahub.py` | Pub/Sub 发布订阅 + TopicPolicy 策略管理 |

---

## AgentLoop 核心方法

| 方法 | 功能 |
|------|------|
| `run(user_input)` | 同步处理用户输入，返回最终响应 |
| `stream_run(user_input)` | 流式处理，实时返回 chunks |
| `_execute_tool_calls(tool_calls)` | 并行执行工具调用 |
| `_maybe_summarize()` | 自动摘要历史（每 N 轮） |
| `clear_history(save_current)` | 清空历史（可选持久化） |

---

## RalphLoop 完成类型

| 类型 | 描述 | 用途 |
|------|------|------|
| `TEST_PASS` | 测试通过率验证 | 代码重构、Bug 修复 |
| `FILE_EXISTS` | 目标文件存在 | 文件生成任务 |
| `MARKER_FILE` | 完成标志文件 | 多步骤工作流 |
| `GIT_CLEAN` | Git 工作区干净 | 全项目变更 |
| `CUSTOM_CHECK` | 自定义验证函数 | 域特定验证 |

---

## Subagent 类型与权限

| 类型 | 权限集 | 用途 |
|------|------|------|
| `EXPLORE` | read_only | 只读探索：搜索文件、阅读代码 |
| `REVIEW` | review | 审查验证：只读 + 代码执行 |
| `IMPLEMENT` | implement | 实现执行：全权限 |
| `PLAN` | plan | 规划分析：只读 + 记忆写入 |

---

## 多智能体协作模式

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| **多脑一手** | 多个 Claude 共享一个 Sandbox | 多角度分析同一份代码 |
| **一脑多手** | 一个 Claude 控制多个 Sandbox | 跨环境执行任务 |
| **多脑多手** | 多个 Claude 各有 Sandbox，通过 Session 协调 | 最复杂多步骤任务 |

---

## 相关文档

- 工具系统：[src/tools/AGENTS.md](tools/AGENTS.md)
- 记忆系统：[memory/AGENTS.md](../memory/AGENTS.md)
- 自主探索：[auto/AGENTS.md](../auto/AGENTS.md)
- 设计文档：[docs/AGENTS.md](../docs/AGENTS.md)