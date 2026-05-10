# 工具注册系统

`src/tools/` 提供工具注册和执行框架，支持动态注册、自动 Schema 推断、同步/异步执行。

---

## 目录结构

| 文件/目录 | 功能 |
|------|---------|
| `__init__.py` | ToolRegistry 类（注册与执行工具） |
| `_registry.py` | ToolRegistry 实现（延迟加载 P2） |
| `_types.py` | ToolKind, PermissionDecision, ToolCapability, ApprovalRequirement 类型 |
| `builtin/` | 核心内置工具（拆分：_file_read, _file_write, _code_execution） |
| `memory/` | L1-L4 记忆系统（拆分：_memory_write, _memory_search, _ttrl, _archive） |
| `skill_loader/` | 动态技能加载（拆分：_loader, _hub, _cache, _index） |
| `ralph_tools_core/` | Ralph Loop 工具（拆分：_start, _status, _completion） |
| `session/` | Session 工具（拆分：_rate_calculation, _history） |
| `subagent_tools_core/` | Subagent 工具（拆分：_sync_tools, _async_tools） |
| `ask_user_types_core/` | Ask User 类型（拆分：_types, _request, _result_state） |
| `vision_api_core/` | 视觉 API（拆分：_capture, _analysis, _utils） |
| `procmem_scanner_core/` | 进程内存扫描（拆分：_types, _winapi, _scan） |
| `builtin_tools.py` | 内置工具门面 |
| `memory_tools.py` | 记忆工具门面 |
| `ralph_tools.py` | Ralph 工具门面 |
| `session_db.py` | SQLite+FTS5 Session 存储 |
| `subagent_tools.py` | Subagent 工具门面 |

---

## ToolRegistry 核心方法

| 方法 | 功能 |
|------|------|
| `register(name, func, schema)` | 注册工具函数 |
| `execute(tool_name, **kwargs)` | 执行工具（支持同步/异步） |
| `get_tool(name)` | 获取工具函数 |
| `get_schemas()` | 返回 JSON Schema 格式（用于 LLM function calling） |

---

## 核心工具（5 个）

| 工具 | 签名 | 功能 |
|------|------|------|
| `file_read` | `(path, start=1, count=100)` | 读取文件内容（带行号） |
| `file_write` | `(path, content, mode="overwrite")` | 写入文件（覆盖/追加） |
| `file_edit` | `(path, old_str, new_str, replace_all=False)` | 编辑文件（精确替换） |
| `code_as_policy` | `(code, language="python", cwd, timeout=60)` | 执行代码（Python/JS/Shell/PowerShell） |
| `ask_user` | `(question, options=None)` | 请求用户输入/确认 |

---

## 记忆工具（L1-L5）

| 层级 | 名称 | 存储 | 用途 |
|------|------|------|------|
| L1 | Index | `notes.md` | 快速参考索引（≤200 字符） |
| L2 | Skills | `skills/*.md` | 可复用操作流程（YAML frontmatter） |
| L3 | Knowledge | `knowledge/*.md` | 跨任务模式和原则 |
| L4 | User Modeling | SQLite | 辩证式用户偏好建模 |
| L5 | Archive | SQLite+FTS5 | 长期工作日志（LLM 摘要） |

**记忆工具方法**：
- `write_memory(level, content, title, metadata)` - 写入指定层级
- `read_memory_index()` - 读取 L1 索引
- `search_memory(keyword, levels)` - 跨层级搜索
- `observe_user_preference(key, value, context, confidence)` - 记录用户偏好
- `get_user_preference(key, context)` - 获取偏好（带例外处理）
- `archive_session_events(session_id, events)` - 归档 Session
- `search_archives(keyword, limit)` - FTS5 全文搜索

---

## Skill Loader（渐进式披露）

**Open Agent Skills 格式**：
```yaml
---
name: skill-name
description: 技能描述
allowed-tools: tool1 tool2
---
```

**SkillLoader 方法**：
- `get_skills_list()` - 返回技能元数据列表
- `get_skills_prompt()` - 生成系统提示注入格式
- `match_skill(query)` - 匹配用户查询到技能
- `load_skill_content(name)` - 加载完整技能内容

---

## Subagent 工具

| 工具 | 签名 | 功能 |
|------|------|------|
| `spawn_subagent` | `(type, prompt, custom_tools, timeout)` | 创建子代理任务 |
| `wait_for_subagent` | `(task_id, timeout)` | 等待任务完成 |
| `aggregate_subagent_results` | `(task_ids, include_errors, max_length)` | 聚合多个结果 |
| `list_subagents` | `(status)` | 列出任务状态 |
| `kill_subagent` | `(task_id)` | 终止任务 |

---

## Ralph 工具

| 工具 | 签名 | 功能 |
|------|------|------|
| `start_ralph_loop` | `(task_prompt_file, completion_type, max_iterations)` | 启动 Ralph Loop |
| `write_completion_marker` | `(content, marker_path)` | 写入完成标记 |
| `check_ralph_status` | `(ralph_id)` | 检查状态 |
| `stop_ralph_loop` | `(ralph_id)` | 停止执行 |
| `create_ralph_task_file` | `(task_name, task_description)` | 创建任务文件 |

---

## Session 数据库（SQLite+FTS5）

**Schema**：
- `session_messages` - 主消息表
- `session_messages_fts` - FTS5 全文搜索（jieba 中文分词）
- `sessions_meta` - 元数据表

**工具**：
- `save_session_history(messages, summary, session_id)` - 保存历史
- `load_session_history(session_id)` - 加载 Session
- `list_sessions(limit)` - 列出最近 Session
- `search_history(keyword, limit)` - FTS5 搜索

---

## ToolKind 分类

| 分类 | 描述 |
|------|------|
| `Read` | 读取操作（安全并发） |
| `Edit` | 编辑操作（需冲突检测） |
| `Write` | 写入操作 |
| `Delete` | 删除操作（需确认） |
| `Execute` | 执行操作 |
| `Search` | 搜索操作（安全并发） |

---

## PermissionDecision 三级权限

| 级别 | 描述 |
|------|------|
| `allow` | 固有安全，直接执行 |
| `ask` | 需用户确认 |
| `deny` | 拒绝执行 |

---

## 相关文档

- 核心引擎：[src/AGENTS.md](../AGENTS.md)
- 记忆系统：[memory/AGENTS.md](../../memory/AGENTS.md)