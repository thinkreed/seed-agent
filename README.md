# seed-superagent

Super-agent 内核（TypeScript，零第三方依赖）：常驻 Router + 并发 Worker、事件驱动、单向状态流、可测试。

设计契约与验收清单：[docs/architecture/super-agent.md](docs/architecture/super-agent.md)。

## 运行（不需要 npm install）

要求 Node.js >= 22.18（自带 TypeScript 类型擦除与 `node:sqlite`）。

```bash
node --test              # 全量测试（142 例，零网络）
node src/cli.ts          # 端到端演示：受理 -> 工单 -> 派工 -> 报告 -> 对外回复 -> 面板
node src/cli.ts remote   # 计算/执行分离演示：daemon 独立进程执行并回报
node src/cli.ts panel seed.db --json   # 机器可读面板
```

配置文件见 `seed.config.example.json`（slots / policy / worker / prepare / 轮询间隔）。

## 结构

| 路径 | 职责 |
|---|---|
| `src/domain.ts` | 领域类型与快照（纯数据） |
| `src/events.ts` + `src/reducer.ts` | 事件表与唯一纯状态推导 |
| `src/fsm.ts` | 工单阶段派生与非法转换 |
| `src/policy.ts` + `src/context.ts` + `src/recall.ts` | 准入、Inline & Spill、链式召回 |
| `src/store.ts` + `src/effects.ts` | 事件表/outbox/cursors、stored work 退避 |
| `src/engine.ts` + `src/actions.ts` + `src/eval_runner.ts` | 唯一状态机驱动者 |
| `src/executor/` + `src/daemon/` | 本地执行器、daemon 协议、远程执行器 |
| `src/sources/` + `src/channels/` | local / GitHub / 飞书 Source 与 Channel |
| `src/react.ts` + `src/jobs.ts` + `src/worker.ts` | 异步 ReAct、后台任务、可唤醒执行会话 |
| `src/watchdog.ts` + `src/control.ts` | 外部控制回路与动作接线 |
| `src/router.ts` + `src/panel.ts` | 面向人的短回复与只读面板 |

## 硬约束（由 `tests/architecture.test.ts` 守护）

1. **状态单向流动**：只有 `store.append()` 能改状态；`reducer.apply()` 是纯函数。
2. **修改收敛单点**：新事件 = `events.ts` + `reducer.ts` + 视图；同类逻辑不许两处。
3. **可测试**：时间只走 `clock.ts`，随机只走 `ids.ts`，测试零网络、零 sleep 依赖。

已知限制见设计文档 §16（Correlation、真实渠道客户端、凭据隔离、Web 面板）。