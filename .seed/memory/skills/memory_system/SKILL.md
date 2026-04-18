---
name: memory-system
description: 四级记忆架构管理技能。触发关键词：记忆、memory、L1/L2/L3/L4、write_memory、沉淀经验。
license: Apache-2.0
metadata:
  author: seed-agent
  version: "1.0"
allowed-tools: write_memory read_memory_index search_memory
---

# 记忆系统技能

## 四级记忆架构

| Level | 目录 | 用途 |
|-------|------|------|
| L1 | notes.md | 全局索引，仅存关键词和路由 |
| L2 | skills/ | 技能沉淀，可复用的操作方案（符合 Open Agent Skills 规范） |
| L3 | knowledge/ | 知识沉淀，领域知识和原理 |
| L4 | raw/ | 原始数据，对话历史、临时产物 |

## 核心 API

### write_memory(level, content, title, metadata)

写入记忆到指定层级。

- L1: 索引追加，不超过 200 字符
- L2: 必须符合 YAML frontmatter 格式（name + description）
- L3/L4: 知识/原始数据存储

### read_memory_index()

读取 L1 全局索引。

### search_memory(keyword, levels)

跨层级搜索关键词。

## 使用原则

- L1 只存索引不存细节
- L2 存可复用的"怎么做"（目录结构：skill-name/SKILL.md）
- L3 存"是什么"和"为什么"
- L4 存原始产物（JSONL 对话历史等）