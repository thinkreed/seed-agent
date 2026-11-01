# @deepseek-ai/dsh-super-agent-core

Super-agent 内核（自 `seed-agent/src` 移植）：领域模型、事件表、reducer、SQLite store、engine、Router/Worker、watchdog、ReAct。

- 约束：单向状态流（`state = reduce(state, event)`，唯一写入口 `store.append()`）、时间走 clock、随机走 ids。
- 该包暂不依赖 cordis；后续 host 插件包会把它接到 DSH 的 LLM/工具/会话上。