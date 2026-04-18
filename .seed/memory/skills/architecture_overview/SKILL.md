---
name: architecture-overview
description: 项目架构导航技能。触发关键词：架构、architecture、项目结构、模块路由、代码位置。
license: Apache-2.0
metadata:
  author: seed-agent
  version: "1.0"
allowed-tools: file_read
---

# 项目架构技能

## 核心模块路由

| 模块 | 路径 | 功能 |
|------|------|------|
| 入口 | main.py | 交互模式/单聊模式，日志初始化 |
| 主循环 | src/agent_loop.py | AgentLoop：上下文管理、工具调度、历史摘要 |
| LLM网关 | src/client.py | LLMGateway：多 provider 异步调用、流式 + 重试 |
| 配置模型 | src/models.py | Pydantic 配置模型、自动迁移 |
| 工具 | src/tools/ | ToolRegistry + 5 核心工具 + 记忆工具 |
| 记忆 | .seed/memory/ | 四级记忆架构 |

## 关键设计

- ToolRegistry: 自动从函数签名推断 JSON Schema
- LLMGateway: 基于 AsyncOpenAI，支持 bailian/zhipu/kimi
- AgentLoop: 每 10 轮自动摘要 + 保存到 L4 raw/sessions
- tenacity: 指数退避重试，空 tools 参数兼容

## 5 核心工具

| 工具 | 功能 |
|------|------|
| file_read | 读取文件（带行号） |
| file_write | 写入文件（覆盖/追加） |
| file_edit | 编辑文件（替换文本） |
| code_as_policy | 执行代码（python/js/shell/powershell） |
| ask_user | 人机协作询问 |