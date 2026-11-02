# 文章逐条核对矩阵（Super-agent / 下一代 Agent Harness）

> 文章：《Super-agent 设计探索：迈向更自主的 Agent 系统》（DeepSeek Harness 团队，2026-10-31）
> 仓库基线：`seed-agent`（TypeScript，零第三方依赖；`src/` 内核 + `contrib/dsh/**` DSH 变种）
> 验证命令：`node --test "tests/*.test.ts"`（244 例，零网络）＋ `node scripts/demo-article.mjs`（22 项现场检查）＋ `node scripts/bench-super-agent.mjs`
> 状态：✅ 已实现且可验证　⚠️ 已实现但有明确边界　❌ 未实现

## 1. 四个基础特征（文章 §1）

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 1.1 | 连续：跨信道/跨会话连续 | Thread + Ticket 多信道 `channelIds`；Trigger 可带多个 Thread 并订阅全部；Router 常驻记忆/对话 | `tests/correlation.test.ts`、`tests/router_session.test.ts` | ✅ |
| 1.2 | 高效：快速响应 + 多任务并发 | 同 tick 多 Thread 批量评估；Worker slot 并发；步级全双工输入 | `docs/bench-super-agent.md`、`tests/react_inputs.test.ts` | ✅ |
| 1.3 | 主动：观察环境并主动推进 | Source 轮询 + Gate + 语义判定 + `speculationSources` 自动投机 | `tests/runner.test.ts`、`tests/source_health.test.ts` | ✅ |
| 1.4 | 持久：在线、接真实环境、异常自愈 | SQLite 事件库 + 重启恢复 + 端侧 daemon + Watchdog | `tests/store.test.ts`、`tests/remote.test.ts`、`tests/watchdog_llm.test.ts` | ✅ |

## 2. 双层架构（文章 §2）

### 2.1 Router 层

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 2.1.1 | 常驻、承接人类交互 | `RouterSession`（host 面板 `chat`；内核 `assessor_router` 默认启用） | `tests/router_session.test.ts`、host `router_session.ts` | ✅ |
| 2.1.2 | 全局序点与记忆 | `memory` + `history` + `observe()` 记录所有进入系统的事件 | `tests/router_session.test.ts`（observe 不触发模型） | ✅ |
| 2.1.3 | 不直接执行任务、可不配 Bash | Router 只有模型与记忆，无工具/沙箱 | 代码分层（`router_session.ts`） | ✅ |
| 2.1.4 | 上一轮推理期间事件合并批处理 | `RouterSession.pending` + `setImmediate` 合并同轮 assess | `tests/router_session.test.ts`（2 Thread → 1 次调用） | ✅ |
| 2.1.5 | 可用更轻量模型 | 内核 `routerModel` 配置；host `llmModel` 与 `dshModel` 分离 | `tests/config.test.ts`、host 配置 | ✅ |
| 2.1.6 | 规模扩大后多层过滤/分片 | 保留 `RouterSession` 接口，未实现分片 | — | ⚠️（文章 §8.1 开放问题） |
| 2.1.7 | 直接回答人的问题（不建工单） | `Decision.kind="reply"`；EvalRunner 产出 `message.queued` 并走 outbox 发送；Router 提示词支持 reply | `tests/reply.test.ts`、`tests/router_session.test.ts`、飞书真机自动回复 | ✅ |
| 2.1.8 | 对话升级为工单 | `chat` 返回可选 `work`；host 用 local Trigger 走正常 Gate/评估/派工；UI 立即可见工单 | `tests/router_dispatch.test.ts`、真机 chat→`tk-000001` | ✅ |

### 2.2 Worker 层

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 2.2.1 | 上下文隔离、完整执行工具 | 每 Ticket 独立 DSH runtime / 内核 worker 目录；内核 worker 有文件/Shell/子代理工具 | `tests/executor.test.ts`、`worker_process.test.ts` | ✅ |
| 2.2.2 | 不直接对人说话，向 Router 汇报 | Worker 只产结构化 `report`；出站由 Router/信道 | `tests/router.test.ts`、host `CHANNELS SMOKE OK` | ✅ |
| 2.2.3 | 订阅 Thread，接收后续事件 | `Subscription` + `fanOut`；同 Thread 可多 Worker 订阅 | `tests/correlation.test.ts`（两个 Worker 同时收到） | ✅ |
| 2.2.4 | 同层 Worker 不直接通信 | 无点对点通道，只靠共享 Thread 扇出 | 同上 | ✅ |
| 2.2.5 | Worker 可再创建 Subagent | 内核 `spawn_subagent`；host 由 DSH runtime 提供 | `tests/subagent_tool.test.ts` | ✅ |
| 2.2.6 | 交回 Router / 取消订阅 | `engine.handback()` / `unsubscribe()`；worker 控制工具 | host `HANDBACK SMOKE OK`、`tests/engine.test.ts` | ✅ |

## 3. 事件驱动（文章 §3）

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 3.1.1 | 程序层 Fast Path（来源/群组/白名单/mention） | `policy.gate`：source/actor 白名单、规则、mention 门槛；订阅直通仍先过 Gate | `tests/policy.test.ts`、`policy_mention.test.ts`、`watchdog_ops.test.ts` | ✅ |
| 3.1.2 | 语义层 Slow Path | `LlmAssessor` / `RouterSession`（含 recall 动作） | `tests/assessor.test.ts`、`router_session.test.ts` | ✅ |
| 3.2.1 | Thread 聚合事件流 | `threadIds` + `Thread` 快照；多 Thread Trigger 形成 Correlation | `tests/correlation.test.ts` | ✅ |
| 3.2.2 | 已订阅直通、未订阅 Router | `engine.ingest` 先 Gate，再 fan-out；未订阅走 Eval | `tests/engine.test.ts`、`correlation.test.ts` | ✅ |
| 3.2.3 | 多对多订阅、Router 观测全部事件 | 订阅表 + `RouterSession.observe` | `tests/correlation.test.ts`、`router_session.test.ts` | ✅ |
| 3.2.4 | Worker 可退订/交回 | `handback` / `unsubscribe` | host `HANDBACK SMOKE OK` | ✅ |
| 3.3.1 | Inline & Spill | `context.buildView` 预算内联、超限落盘/引用 | `tests/context.test.ts` | ✅ |
| 3.3.2 | 链式召回（对象 ID + 下一跳 ID） | `recall()` 返回 summary + handles；DSH 工具/索引 | `tests/recall.test.ts` | ✅ |
| 3.3.3 | 多跳按需展开 | 每次 recall 内联下一跳句柄，工具可逐跳调用 | `RECALL TOOL SMOKE OK` | ✅ |
| 3.3.4 | 时空相邻内容 | 同 Thread 历史事件一并内联（`AssessContext.history`）；平台侧"前后相邻消息/被回复消息"由 Source 提供的 Trigger 历史覆盖 | `tests/context.test.ts` | ✅（依赖来源提供历史） |
| 3.4.1 | 投机执行，有价值才交付 | 内核 `Speculator`（来源策略/去重/并发/超时/交付闸门）+ `reactSpeculationRunner`；host `speculate()`/`speculationSources` 复用 core Speculator，DSH runtime 执行 | `tests/speculation.test.ts`、demo §3.4、host `SPECULATION SMOKE OK`（真实模型） | ✅ |

## 4. 面向人的交互（文章 §4）

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 4.1.1 | start() 立即返回 Started | `jobs.start` 返回 jobId；`super_agent_start` 工具 | `tests/jobs.test.ts`、host `ASYNC REACT SMOKE OK` | ✅ |
| 4.1.2 | stop() 终止长命令 | `jobs.stop` + AbortSignal；`super_agent_stop` | `tests/jobs.test.ts` | ✅ |
| 4.1.3 | 完成后结果作为新事件回灌 | 内核 `nextNotice` → 新输入；host 控制文件 → `reply` 注入 | `tests/session_inputs.test.ts` | ✅ |
| 4.1.4 | 全双工：步级处理新输入 | `ReactLoop.nextInputs` 每步注入；WorkerSession 自动排空 | `tests/react_inputs.test.ts` | ✅ |
| 4.2.1 | IM 低打扰 ≤100 字 | `format.compactForIm`；`chat(channel="im")` 规范 | `tests/channels_outbox.test.ts`、`router_session.test.ts` | ✅ |
| 4.2.2 | GitHub/邮件/文档结构化 | `structureForAsync` + `ChannelFormattingWriter`；`.md`/`.eml` 草稿 | `tests/channels_outbox.test.ts`、`CHANNEL FORMAT LIVE OK`（飞书 + GitHub 真发） | ✅ |
| 4.2.3 | IM 真机送达 | 飞书 `im/v1/messages`；`CHANNELS SMOKE OK` | 群消息 id `om_x100b61bcf475f0acdf704d1264b1e7c` | ✅ |

## 5. 计算、状态与环境分离（文章 §5）

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 5.1 | 计算无状态、状态入库、重启恢复 | 全部状态为事件表；`recoverAfterRestart` 收口 running assignment | `tests/store.test.ts`、host `RESTART SMOKE OK` | ✅ |
| 5.2.1 | 执行环境留在原地，端侧轻量 daemon | 内核 stdio/HTTP daemon；host HTTP daemon + `remote_*` 工具 | `tests/remote.test.ts`、`remote_http.test.ts`、host `DAEMON SMOKE OK` | ✅ |
| 5.2.2 | BYOM、跨设备切换 | HTTP 传输 + 多设备 `SUPER_AGENT_DAEMONS`/`device` 参数 | `tests/remote_http.test.ts`、host tool-remote | ✅ |
| 5.2.3 | 间歇在线设备自动恢复 | `HttpTransport.onReconnect` → `RemoteExecutor.recover()` 重拉/补投 | `tests/remote_http.test.ts`、`remote.test.ts` | ✅ |

## 6. Watchdog（文章 §6）

| # | 文章要求 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 6.1 | 主系统外独立控制回路 | host `DshWatchdogJudge` 独立 DSH 会话；内核 `Watchdog` + 定时 Daemon | host `WATCHDOG SESSION SMOKE OK`；`tests/daemon.test.ts` | ✅ |
| 6.2 | 基础设施故障 | stalled / undelivered / `source.failed` findings | `tests/source_health.test.ts` | ✅ |
| 6.3 | 模型判断是否真推进/跑偏 | `LlmWatchdogJudge` 带最近报告、原始请求、assignment；有 open 工单即裁定 | `tests/watchdog_llm.test.ts` | ✅ |
| 6.4 | 介入与持续复查 | retry/applyPolicy；host 15s 复查 | `tests/control.test.ts`、host `rechecks=1` | ✅ |
| 6.5 | 自然语言询问/在线改规则 | `Watchdog.ask()`、`Engine.setPolicy()`、host `watchdog`/`policy` 命令、面板 Ask/Apply | `tests/watchdog_ops.test.ts`、`tests/watchdog_llm.test.ts` | ✅ |

## 7. 实验（文章 §7）

| # | 文章内容 | 实现 | 验证 | 状态 |
|---|---|---|---|---|
| 7.1 | Router 批处理定量 | 确定性假模型 + 可选真实模型 | `docs/bench-super-agent.md` | ✅（机制级） |
| 7.2 | 四形态消融 | Super-agent / 去直通 / 单 session 中性 / 优先委派 | 同文档；`node scripts/bench-super-agent.mjs` | ✅（机制级） |

## 8. 开放问题（文章 §8，非验收项）

| 文章问题 | 当前处理 | 状态 |
|---|---|---|
| 双层架构扩容、Router 分片 | 单常驻 Router；留接口 | 开放 |
| 跨月长程记忆 | 链式召回 + 事件库；无跨月记忆策略 | 开放 |
| 脱离 Session 的产品化交互 | 面板/CLI/信道；非本文重点 | 开放 |
| A2A / 组织级上下文边界 | 未实现（文章开放问题） | 开放 |
| 强安全隔离/凭据使用 | daemon 只做最小隔离，凭据不进模型上下文 | 开放（文章 §8.4） |

## 9. 已知工程边界（不改变上述结论）

- DSH host/core 已在 vendor checkout 上实际构建：`pnpm run build` 10/10 gates，core/host smoke 通过；真实模型 smoke 覆盖 SDK/speculation/async/full-duplex/daemon/router/assessor/watchdog/recall-tool。
- 内核真实模型链路已验证：Router→Worker→工具写文件（`kernel-real.txt` = ok）。
- HTTP daemon 为明文 HTTP + Bearer token，默认 `127.0.0.1`。
- 邮件/文档为草稿语义，不直连 SMTP/在线文档 API。
- Correlation 需 Trigger 显式携带多个 Thread；未做语义自动关联。

## 10. 生产就绪增量（2026-11-02）

| 项 | 实现 | 验证 | 状态 |
|---|---|---|---|
| Worker 环境最小化 | 只透传基础变量 + 模型 key；飞书/GitHub 等凭据不进 worker | `tests/worker_env.test.ts` | ✅ |
| daemon 非本机鉴权 | 非 loopback 监听必须 `SA_DAEMON_TOKEN`，否则拒绝启动 | `tests/remote_http.test.ts` | ✅ |
| SQLite 备份/恢复 | `VACUUM INTO` 一致快照 + 回放哈希校验 | `tests/backup.test.ts`、`scripts/backup-super-agent.mjs` | ✅ |
| 吞吐/soak | WAL + `synchronous=NORMAL`；5000 事件/20012 events/≈1600 events/s | `tests/soak.test.ts`、`scripts/soak-super-agent.mjs` | ✅ |
| 长跑 soak | 持续追加 + 重复投递 + 周期性重启 + 重放校验，可断点续跑 | `scripts/soak-long-super-agent.mjs`（`LONG SOAK OK`） | ✅ |
| 模型重试/超时/脱敏 | 5xx/429 按 Retry-After 退避、超时中断、错误里 `sk-`/Bearer 脱敏 | `tests/model_retry.test.ts` | ✅ |
| 故障注入 | 模型 5xx/429/超时、daemon 坏 JSON 仍健康、磁盘/DB 路径错误启动失败、source/daemon 离线恢复、重复事件幂等 | `tests/model_retry.test.ts`、`tests/faults.test.ts`、`tests/source_health.test.ts`、`tests/soak.test.ts` | ✅ |
| daemon 指标 | `/metrics` Prometheus 文本（请求/错误/事件缓冲/uptime） | `tests/remote_http.test.ts` | ✅ |
| daemon TLS | 内置 `tls:{cert,key}` HTTPS；也支持反向代理终止 TLS | `tests/remote_http.test.ts`（证书缺失拒绝启动） | ✅ |
| 部署资产 | Dockerfile、systemd 加固单元、生产部署手册 | `deploy/` | ✅ |
| worker 容器隔离 | 仍为宿主 shell + 工单目录 | `deploy/README.md` | ⚠️ |