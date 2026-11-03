# 外部审计对账（2026-11-03）

对另一智能体的审计逐条核对。状态以当前代码和测试为准；审计提到的“248 例跑不了”是沙箱/旧快照问题，当前为 251 例全绿。

| 审计项 | 现状 | 证据 |
|---|---|---|
| Router 记忆重启即丢 | ✅ 已修 | `<dbPath>.router-chat.json` + `.router-dsh-session.json`；DSH `resumeSession()` |
| 投机执行内核未接线 | ✅ 已接线（opt-in） | `src/app_speculation.ts`；`SourceRunner.onIngested`；配置 `speculationSources`；`tests/speculation_app.test.ts` |
| 内核 Worker 无链式召回 | ✅ 已补 | `src/recall_index.ts` 写 `recall-index.json`；worker 新增 `recall` 工具；`tests/recall_index.test.ts` |
| Watchdog advisor 未注入 | ✅ 已注入 | `App` 构造 `LlmWatchdogAdvisor`；自然语言问诊可用 |
| 双份内核分叉 | ⚠️ 仍存在 | `src/**` 与 `contrib/dsh/packages/super-agent/core/src/**` 仍有手维护副本；本次已同步共享文件，但未合并 |
| `onReconnect` 未接线 | ⚠️ 仍存在 | 仅 `src/executor/http.ts` 定义；设备重连自动恢复未在 App 主路径使用 |
| §5 云端无状态计算 | ⚠️ 架构边界 | 当前是单机事件溯源 + SQLite；云端拆分未实现 |
| §7 真实模型批处理实验 | ⚠️ 仍为机制级 | 假模型时间线 + 真机验收，未跑批量真实模型实验 |
| 飞书回复被压缩 | ✅ 已修 | host 本地 `format.ts` 对 `fs:`/`feishu:` 不压缩；API 读回 258 字节完整 |
| 工单标题无语义 | ✅ 已修 | Router `Decision.title` → `Ticket.title`；真机标题 `Create title-check.txt with ok` |
| 受理后无即时反馈 | ✅ 已修 | Router 在报告前先发 `ack:<ticketId>`：`已收到，正在处理：<title>`；`tests/ack.test.ts` |

## 剩余工作

1. **合并双内核**：把 `contrib/dsh/.../core` 改成由 `src` 生成的副本，或反向让内核只保留一份共享包。
2. **`onReconnect` 接线**：HTTP executor 断线重连后自动 replay/resume。
3. **§5 存算分离**：SQLite 单机之外的远程状态/无状态计算。
4. **§7 真实批处理**：用真实模型跑多时间线实验并产出统计。

前两项是代码级缺口，后两项是文章目标里的架构/实验缺口；不能靠补测试声称完成。