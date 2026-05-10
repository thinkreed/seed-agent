# 设计文档目录

架构决策、实现方案和技术规范的权威参考。

---

## 文档索引

| 文档 | 描述 |
|------|------|
| `wiki_knowledge_integration_analysis.md` | Wiki 知识落地分析（P0-P5 全部优化点） |
| `memory_graph_enhancement_design.md` | Memory Graph 架构（技能进化 + 成果追踪） |
| `L4_SQLite_FTS5_Design.md` | L4 Session 存储迁移（JSONL → SQLite+FTS5） |
| `long_cycle_loop_enhancement_design.md` | Ralph Loop 架构和实现设计 |
| `ralph_loop.md` | Ralph Loop 概念和动机 |
| `rate_limiting_system_design.md` | LLM 请求限流系统（Token Bucket + Queue） |
| `request_queue_turn_ticket_design.md` | Request Queue TurnTicket 公平调度 |
| `credential_security_design.md` | 凭证安全设计（Vault + Proxy 架构） |
| `harness/` | Harness 系列设计文档（6 个子文档） |

---

## P4+P5 新功能模块

| 功能 | 文件位置 | 描述 |
|------|----------|------|
| **Circuit Breaker** | `src/client/_circuit_breaker.py` | Provider 熔断器（连续失败自动切换） |
| **Orphan Reaper** | `src/subagent_manager_core/_orphan_reaper.py` | 孤儿进程回收（两阶段终止） |
| **Stampede Protection** | `src/request_queue_core/_stampede.py` | 缓存击穿保护（单请求执行，共享结果） |
| **Complexity Scorer** | `src/client/_complexity_scorer.py` | 23 维度评分 → 四级 Tier 路由 |
| **Specificity Detector** | `src/client/_specificity_detector.py` | 任务类型检测 → 专用模型路由 |
| **Merkle DAG** | `src/core/_merkle_dag.py` | 增量索引（O(1) 无变更检测） |
| **DataHub** | `src/core/_datahub.py` | Pub/Sub 发布订阅 + TopicPolicy |
| **QueryInvalidator** | `src/core/_query_invalidator.py` | 失效策略 + 缓存管理 |

---

## 文档与代码关联

| 文档 | 相关代码 |
|------|----------|
| Memory Graph Design | `src/tools/skill_loader/`, `src/tools/session/` |
| L4 SQLite Design | `src/tools/session_db.py` |
| Ralph Loop Design | `src/ralph_loop.py`, `src/autonomous/` |
| Rate Limiting Design | `src/rate_limiter.py`, `src/request_queue.py` |

---

## 相关文档

- 核心引擎：[src/AGENTS.md](../src/AGENTS.md)
- 工具系统：[src/tools/AGENTS.md](../src/tools/AGENTS.md)