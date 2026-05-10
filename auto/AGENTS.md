# 自主探索 SOP 模块

空闲时自主执行任务，监控用户活动并在 2 小时空闲后自动触发 SOP 驱动的探索任务。

---

## 触发条件

- **空闲超时**：2 小时（可通过 `src/shared_config.py` 的 `AutonomousConfig.idle_timeout_hours` 配置）
- **监控机制**：每 30 秒检查空闲时间

---

## Ralph Loop 集成

| 机制 | 配置 | 功能 |
|------|------|------|
| **完成承诺检测** | `~/.seed/completion_promise` | 外部标记驱动退出（DONE/COMPLETE/TASK_FINISHED） |
| **上下文重置** | 每 5 轮迭代 | 防止漂移，提取关键上下文 |
| **状态持久化** | `~/.seed/ralph_state.json` | 崩溃恢复 |
| **安全上限** | 1000 轮 / 8 小时 | 最大迭代和时长保护 |

---

## SOP 流程

1. **检查 TODO.md** → 存在任务则执行模式，否则规划模式
2. **执行模式** → 逐项处理，`<thinking>` 内推演
3. **规划模式** → 生成 5-7 TODO 项（格式：`[ ] Type | Goal | Criteria | 沉淀`）

---

## 价值公式

> **实际执行可落地性 × 进化沉淀价值**

---

## 长期战略任务（STR）

| 任务 | 来源 | 目标 |
|------|------|------|
| **STR-01** | `$WIKI_HOME/` | 外部知识迁移 → PR/Skill/L3 |
| **STR-02** | GenericAgent `memory/` | 吸收自动化 SOP → L2 Skills |
| **STR-03** | `skills/` | 基因压缩（信号+策略+约束+验证）→ 减少 50%+ Token |
| **STR-04** | `memory/` L1-L5 | Auto-Dream 清理策略 |

---

## 记忆集成（L1-L5）

| 层级 | 使用方式 |
|------|----------|
| L1 | 触发词路由 SOP 选择 |
| L2 | 任务驱动的技能选择 |
| L3 | 决策的历史模式 |
| L4 | `get_user_preference()` 适配用户偏好 |
| L5 | `search_archives()` 搜索历史解决方案 |

---

## 失败升级协议

| 次数 | 行动 |
|------|------|
| 1 次 | 重试操作 |
| 2 次 | 探测根因，调整策略 |
| 3 次 | 换方案或询用户 |

---

## 核心原则

- **不推诿**：无方案时提建议
- **有逻辑**：每步 `<thinking>` 推演
- **重沉淀**：任务结束必总结，调用 `start_long_term_update()`
- **懂用户**：使用 L4 工具观察和适配用户偏好

---

## 文件索引

| 文件 | 描述 |
|------|------|
| `自主探索 SOP.md` | 自主探索详细 SOP（中文） |
| `src/autonomous/` | AutonomousExplorer 实现（模块化拆分） |
| `src/ralph_loop.py` | Ralph Loop 实现 |
| `src/tools/ralph_tools.py` | Ralph 管理工具 |

---

## 相关文档

- 核心引擎：[src/AGENTS.md](../src/AGENTS.md)
- 记忆系统：[memory/AGENTS.md](../memory/AGENTS.md)
- Ralph 设计：[docs/long_cycle_loop_enhancement_design.md](../docs/long_cycle_loop_enhancement_design.md)