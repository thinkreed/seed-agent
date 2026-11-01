# seed-superagent

Super-agent 内核：常驻 Router + 并发 Worker、事件驱动、单向状态流、可测试。

设计契约在 [docs/architecture/super-agent.md](docs/architecture/super-agent.md)（领域模型、状态机、单点收敛表、分期计划）。本目录只放代码。

## 运行（零依赖，不需要 npm install）

要求 Node.js >= 22.18（自带 TypeScript 类型擦除与 `node:sqlite`）。

```bash
node src/cli.ts            # 端到端演示：Trigger -> Eval -> Ticket -> Assignment -> Report
node --test                # 全部测试（不联网、不 sleep）
```

## 结构

| 路径 | 职责 |
|---|---|
| `src/domain.ts` | 领域类型与快照（纯数据） |
| `src/events.ts` | 事件信封、类型表、构造器 |
| `src/reducer.ts` | 唯一纯状态推导 |
| `src/fsm.ts` | 工单阶段派生与转换检查 |
| `src/policy.ts` | 确定性准入（Gate）与 Policy 版本 |
| `src/store.ts` | 事件表 + outbox + cursors（SQLite） |
| `src/effects.ts` | stored work：先落库、后执行、退避重试 |
| `src/engine.ts` | 唯一状态机驱动者 |
| `src/panel.ts` | 只读面板（只列待人工项） |
| `src/runtime.ts` | 端口装配（唯一接线处） |

## 硬约束

1. **状态单向流动**：只有 `store.append()` 能改状态；`reducer.apply()` 纯函数。
2. **修改收敛单点**：新增事件改 3 处（events 类型表 / reducer 分支 / 视图）；新增来源改 `sources/` 一个包。
3. **易于测试**：端口可替换、时钟注入、回放确定、测试无网络无 sleep。

这些约束由 `tests/architecture.test.ts` 守护。