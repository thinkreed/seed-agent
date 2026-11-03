# 外部审计对账（2026-11-03）

对另一智能体的审计逐条核对。状态以当前代码和测试为准；审计提到的“248 例跑不了”是沙箱/旧快照问题，当前为 253 例全绿。

| 审计项 | 现状 | 证据 |
|---|---|---|
| Router 记忆重启即丢 | ✅ 已修 | `<dbPath>.router-chat.json` + `.router-dsh-session.json`；DSH `resumeSession()` |
| 投机执行内核未接线 | ✅ 已接线（opt-in） | `src/app_speculation.ts`；`SourceRunner.onIngested`；配置 `speculationSources`；`tests/speculation_app.test.ts` |
| 内核 Worker 无链式召回 | ✅ 已补 | `src/recall_index.ts` 写 `recall-index.json`；worker 新增 `recall` 工具；`tests/recall_index.test.ts` |
| Watchdog advisor 未注入 | ✅ 已注入 | `App` 构造 `LlmWatchdogAdvisor`；自然语言问诊可用 |
| 双份内核分叉 | ✅ 已消除 | `contrib/.../core/src` 已删除；core 的 `build.mjs` 直接编译仓库根 `src/**`，不再存在第二份内核源码 |
| `onReconnect` 未接线 | ✅ 已接线 | `AppExecutor` 远端路径：`HttpTransport.onReconnect → RemoteExecutor.recover()`；`remote` 配置解析 + `closeAll` |
| §5 云端无状态计算 | ⚠️ 架构边界 | 当前是单机事件溯源 + SQLite；云端拆分未实现 |
| §7 真实模型批处理实验 | ✅ 已跑 | `scripts/experiment-real-batch.mjs`：4 线程，1 次批量 2.09s vs 逐条 4.93s，2.36x；逐条缓存命中 93.2%，见 `docs/experiment-batch-real.json` |
| 飞书回复被压缩 | ✅ 已修 | host 本地 `format.ts` 对 `fs:`/`feishu:` 不压缩；API 读回 258 字节完整 |
| 工单标题无语义 | ✅ 已修 | Router `Decision.title` → `Ticket.title`；真机标题 `Create title-check.txt with ok` |
| 受理后无即时反馈 | ✅ 已修 | Router 在报告前先发 `ack:<ticketId>`：`已收到，正在处理：<title>`；`tests/ack.test.ts` |

## 剩余工作

1. **§5 存算分离**：SQLite 单机之外的远程状态/无状态计算。