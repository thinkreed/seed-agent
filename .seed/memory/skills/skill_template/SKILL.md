---
name: skill-template
description: Agent Skill 规范模板，用于创建符合 Open Agent Skills 标准的技能。
license: Apache-2.0
compatibility: 无特殊要求
metadata:
  author: seed-agent
  version: "1.0"
---

# Skill 使用说明

本文件为 Agent Skill 规范模板，遵循 [Open Agent Skills](https://openagentskills.dev/zh/docs/specification) 标准。

## Frontmatter 必需字段

| 字段 | 约束 |
|------|------|
| `name` | 1-64字符，小写字母/数字/连字符，不以 `-` 开头/结尾，无连续 `--` |
| `description` | 1-1024字符，描述功能和触发时机 |

## Frontmatter 可选字段

| 字段 | 说明 |
|------|------|
| `license` | 许可证名称 |
| `compatibility` | 环境要求（最多500字符） |
| `metadata` | 键值对（如 author, version） |
| `allowed-tools` | 预批准工具列表（空格分隔） |

## 目录结构

```
skill-name/
├── SKILL.md          # 必需：frontmatter + 指令
├── scripts/          # 可选：可执行脚本
├── references/       # 可选：附加文档
└── assets/           # 可选：静态资源
```

## 正文建议内容

- 分步执行指令
- 输入/输出示例
- 常见边缘情况处理
- 文件引用（相对路径）

## 示例 Skill

```yaml
---
name: file-read
description: 读取文件内容并返回带行号的文本。触发关键词：读取、file_read、查看文件。
license: Apache-2.0
metadata:
  author: seed-agent
  version: "1.0"
allowed-tools: file_read
---

# 文件读取技能

## 使用方法

调用 `file_read` 工具：
- path: 文件路径（绝对或相对）
- start: 起始行号（默认1）
- count: 行数（默认100）

## 输出格式

返回带行号的内容，如：
```
1|import os
2|import sys
```

## 边缘情况

- 文件不存在：返回错误信息
- 路径相对：自动从项目根目录解析
```