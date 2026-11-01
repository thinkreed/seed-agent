# 对照文章的总验收（Super-agent 设计探索 → DSH fork 变种）

文章：DeepSeek Harness 团队《Super-agent 设计探索：迈向更自主的 Agent 系统》（2026-10-31）
实现：`seed-agent` 仓库中的 DSH fork 变种（`contrib/dsh/**` + `scripts/**` + `docs/**`）
验收命令：`pwsh -File scripts/verify-super-agent.ps1 -Slow`（可选 `-Network` 追加真实飞书/GitHub）

状态说明：✅ 已实现且有真机证据 ｜ ⚠️ 有实现但有明确边界 ｜ ❌ 未实现（在已知边界列出）

## 1. 文章 §2 双层架构

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 常驻 Router 层承接人类交互 | `RouterSession`（记忆、对话历史、`chat`） | `ROUTER SMOKE OK`（`lastBatch threads=2`）、面板 Router 对话截图 `docs/dsh-desktop-router.png` | ✅ |
| Router 全局序点 / 批处理 | 同一 tick 多 Thread 合并为一次模型调用 | `docs/bench-super-agent.md`：批量 1 call/43ms vs 串行 4 calls/179ms | ✅ |
| Router 不执行具体任务 | Router 只做决策/回复；工具在 Worker | 代码分层 + 面板对话 | ✅ |
| Worker 上下文隔离、完整工具 | 每 Ticket 独立 DSH runtime + 工作目录 | `DSH EXECUTOR SMOKE OK`（产物落 `tickets/<id>`）、`RESTART SMOKE OK` | ✅ |
| Worker 不直接对人说话，Router 统一回复 | Worker 只产 report；出站由 Router/模板 + 信道格式化 | `CHANNELS SMOKE OK` | ✅ |
| Worker 间不直接通信，靠订阅获知 | 订阅扇出、无点对点通道 | `FANOUT SMOKE OK`（`fanned_out`） | ✅ |
| 多对多订阅 / handback | 订阅 + `handback/unsubscribe` | `HANDBACK SMOKE OK`（交回→新工单） | ✅ |

## 2. 文章 §3 事件驱动

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| Trigger 源接入（IM/GitHub） | 飞书/GitHub/JSONL Source + 轮询 + bot 自消息过滤 + 幂等 | `SOURCES SMOKE OK`、`INBOUND LIVE OK`（飞书 3 消息/1 trigger）、桌面 `sources=feishu+github` | ✅ |
| Fast Path 程序准入 | Gate（sender 白名单 + source/actor 规则） | `HOST SMOKE OK`、策略代码 | ✅ |
| Slow Path 语义策略 | LLM Router/assessor 判定 | `ROUTER SMOKE OK`（建单/闲聊） | ✅ |
| Thread 概念与路由（订阅直通） | threadId → 订阅 → 直通 Worker | `FANOUT SMOKE OK` | ✅ |
| 未订阅事件由 Router 观测 | 全部 Trigger 落库，只评估未订阅 | `FANOUT SMOKE OK` | ✅ |
| Inline & Spill | 指令超限落盘 + prompt 给路径；召回索引 | `SPILL SMOKE OK`、`docs/dsh-variant.md` | ✅ |
| 链式召回（trigger→thread→ticket） | `super_agent_recall` DSH 工具 + 索引 | `RECALL SMOKE OK`、`RECALL TOOL SMOKE OK`（worker 逐跳取回索引-only marker） | ✅ |
| 投机执行（有价值才交付） | `speculate()` 独立 runtime，`{deliver}` 判定 | `SPECULATION SMOKE OK`（交付→channel；闲聊→静默） | ✅ |

## 3. 文章 §4 面向人的交互

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 异步 ReAct start/stop，Started 不阻塞 | `super_agent_start/status/stop` 后台命令工具 | `ASYNC REACT SMOKE OK`（start 立即返回、running→done） | ✅ |
| 全双工：后台工作期间可接新指令 | 回合中消息排队，回合结束立即作为下一轮 | `FULL DUPLEX SMOKE OK`（turns=2、队列排空） | ✅ |
| IM 低打扰（≤100 字） | `format.ts` IM 压缩、去 Markdown | `CHANNEL FORMAT SMOKE OK`（94 字）、`CHANNEL FORMAT LIVE OK`（飞书 `om_x100b…`） | ✅ |
| GitHub/异步信道结构化 | 标题/结论/落款结构化交付 | `CHANNEL FORMAT LIVE OK`（GitHub 评论 `gh-thinkreed/seed-agent-e2e-3`） | ✅ |

## 4. 文章 §5 计算、状态与环境分离

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 计算与状态分离 | host 无状态逻辑 + SQLite 事件库；重启恢复 | `RESTART SMOKE OK`（recovery events=2、live assignment） | ✅ |
| 计算与执行环境分离（端侧 daemon） | 无状态 daemon（exec/read/write、token、路径约束）+ `super_agent_remote_*` | `DAEMON SMOKE OK`（产物在 daemon root、不在工单目录） | ✅ |

## 5. 文章 §6 Watchdog

| 文章要求 | 实现 | 证据 | 状态 |
|---|---|---|---|
| 主系统外巡检 | 定时确定性 findings（stalled/undelivered） | `HOST SMOKE OK`（watchdog ok 0） | ✅ |
| 模型判断是否要介入 | `LlmWatchdogJudge` 注入 | `WATCHDOG LLM SMOKE OK`（确定性 intervene vs 模型判 benign ok） | ✅ |
| 介入与复查 | retry + 15s 复查 + intervention 记录 | 同上（rechecks=1） | ✅ |
| 被自然语言询问/在线改行为 | 未实现（面板 Router 对话可问状态，但不能改规则） | — | ❌ |

## 6. 文章 §7 实验

| 内容 | 实现 | 证据 | 状态 |
|---|---|---|---|
| Router 批处理定量 | 确定性假模型 + 可选真实模型 | `docs/bench-super-agent.md`（≈4×；真实 3 threads 1 call） | ✅ |
| 消融（单 session vs Super-agent） | 机制级模拟 | `docs/bench-super-agent.md`（≈2×） | ✅ |

## 7. 原型文档 001–008 的语义

| 文档 | 覆盖 | 状态 |
|---|---|---|
| 001 domain | Ticket stages、Mandate、Assignment、Subscription、Policy 版本、Eval 无状态 | ✅（Correlation 未实现） |
| 002 authorization | Gate/LLM 两级、handback、resume | ⚠️（mention/direct 准入表、bot 白名单未细做） |
| 003 execution | 工单目录、执行器隔离、重启恢复、outbox | ⚠️（worker slot 用 `slots`；后台期限依赖 watchdog） |
| 004 prompts | 评估/Worker/Router 提示词 | ⚠️（无分层/版本拼装） |
| 005 panel | 工单/时间线/搜索/stage/配置摘要/Router 对话 | ⚠️（设置页与事件跳转未做） |
| 006 deployment | 一键桌面脚本、隔离 DSH_HOME、验收脚本 | ✅ |
| 007 architecture | 插件化模块、host/executor/channels 分层 | ✅ |
| 008 cookbook | 新增 Source 的路径可复制 | ✅ |

## 8. 桌面交付

| 项 | 状态 | 说明 |
|---|---|---|
| 桌面应用（Electron） | ✅ | 窗口标题/侧栏品牌 `seed-agent`，Super-agent 面板 |
| 品牌：productName/协议名 | ✅ | apply 脚本把安装包 `productName`/协议名替换为 `seed-agent` |
| 品牌：hero/托盘/安装包图标 | ⚠️ | hero 文案与托盘图标仍是 DSH 原样 |
| 安装包 | ✅（首启为基础形态） | `dist/seed-agent-0.2.2-alpha.2-win-x64-unsigned.exe`（301.7 MB，SHA256 `27F2D1…7E11B9`）：静默安装退出码 0、`seed-agent.exe` 可启动并拉起 dsh web；Super-agent 面板需准备 profile（尚未烘进安装包，见 `docs/packaging.md`） |

## 9. 已知边界（诚实清单）

1. 链式召回是一跳/索引式的：工具可逐跳展开，但没有按事件 id 的多级持久索引与自动摘要压缩。
2. 异步 ReAct 的"后台完成自动作为事件投递"用轮询 `super_agent_status` 实现；DSH 原生异步工具未接入。
3. Router 是单个常驻会话；未做文章提到的多层过滤/分片。
4. Watchdog 不能被自然语言询问、不能在线改主系统行为。
5. 面板缺设置页、事件详情跳转；工单搜索仅本地过滤。
6. 渠道：IM 压缩 + GitHub 结构化已验；邮件/文档信道未接入。
7. daemon 只覆盖 exec/read/write；未做 SSH/远端沙箱与凭证管理。
8. 打包：无签名、无自动更新；hero/托盘品牌未改。
9. benchmark 是机制级（假模型固定延迟），不是真实模型能力对比。

## 10. 复现命令

```powershell
pnpm --dir dsh install
pwsh -File scripts/apply-dsh-patches.ps1 -Repo .
pwsh -File scripts/desktop-super-agent.ps1 -Restart
pwsh -File scripts/verify-super-agent.ps1 -Slow        # 19 项
pwsh -File scripts/verify-super-agent.ps1 -Network     # 追加飞书/GitHub 真发
node scripts/bench-super-agent.mjs --real              # §7 实验（真实模型可选）
```

证据索引：`docs/dsh-desktop-*.png`、`docs/bench-super-agent.md`、host `tests/*-smoke.mjs`。