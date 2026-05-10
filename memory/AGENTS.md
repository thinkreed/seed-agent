# 记忆管理 SOP 模块

提供 Seed Agent 的记忆管理系统，支持持久学习、技能组织和知识进化。

---

## 记忆层级（L1-L5）

| 层级 | 名称 | 存储 | 用途 |
|------|------|------|------|
| **L1** | Index | `notes.md` | 快速参考索引（≤200 字符/条，无代码块） |
| **L2** | Skills | `skills/*.md` | 可执行 SOP（YAML frontmatter + Markdown） |
| **L3** | Knowledge | `knowledge/*.md` | 跨任务模式、原则、环境配置 |
| **L4** | User Modeling | SQLite | 辩证式用户偏好建模（例外处理 + 置信度） |
| **L5** | Archive | SQLite+FTS5 | 长期工作日志（LLM 摘要 + jieba 分词） |

---

## L2 Skills 格式要求

```yaml
---
name: skill-name          # 必填：1-64 字符，小写字母/数字/连字符
description: 描述         # 必填：≤1024 字符
allowed-tools: tool1 tool2  # 可选：允许的工具列表
---
```

---

## L4 用户建模（黑格尔辩证式）

**核心理念**：渐进理解用户，允许例外和复杂情况

**Schema**：
- `user_profiles` - 偏好存储（带例外）
- `user_observations` - 观察记录队列
- `dialectical_history` - 进化历史追踪

**进化示例**：
```
旧: "用户偏好美式咖啡"
新证据: "用户点了拿铁" (context: 周三下午)
冲突检测 → 例外处理
升级: { usual: "美式", exceptions: { "周三下午": "拿铁" } }
```

---

## L5 归档（LLM 摘要 + FTS5）

**流程**：
1. 提取 Session 事件
2. LLM 生成 1-2 句核心结论
3. 提取 3-5 关键发现
4. FTS5 索引存储（jieba 分词）

---

## 核心工具

| 工具 | 功能 |
|------|------|
| `write_memory(level, content, title)` | 写入指定层级 |
| `read_memory_index()` | 读取 L1 索引 |
| `search_memory(keyword, levels)` | 跨 L1-L3 搜索 |
| `observe_user_preference(key, value, context, confidence)` | L4 记录偏好 |
| `get_user_preference(key, context)` | L4 获取偏好（带例外） |
| `archive_session_events(session_id, events)` | L5 归档 |
| `search_archives(keyword, limit)` | L5 FTS5 搜索 |
| `get_memory_hierarchy()` | 获取所有层级摘要 |

---

## Auto-Dream 记忆整理

**触发**：Scheduler 内置任务，每 12 小时

**流程**：L1 → L2 → L3 → L4 → L5 逐层检查 → ROI 评估 → 低价值清理

**ROI 公式**：`(错误概率 × 操作成本) / 存储成本`

---

## 数据流向

```
L5 (archives) → 归档摘要 → L3 (knowledge)
                    ↓
L4 (user_modeling) → 用户偏好洞察
                    ↓
L4 (raw/sessions) → L2 (skills) → L3 (knowledge)
       ↓                    ↓             ↓
       └──────────────── L1 (notes) ←─────┘
```

---

## 文件索引

| 文件 | 描述 |
|------|------|
| `memory.md` | 核心记忆管理 SOP（层级定义、约束规则） |
| `auto_dream.md` | Auto-Dream 记忆整理 SOP（ROI 评估、清理策略） |

---

## 相关文档

- 工具系统：[src/tools/AGENTS.md](../src/tools/AGENTS.md)
- 自主探索：[auto/AGENTS.md](../auto/AGENTS.md)