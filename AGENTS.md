# seed-agent — 给 agent 的工作指南

这是一个 Super-agent 内核的 **TypeScript 重写**（无历史包袱，旧 Python 代码已全部删除，见 `main` 分支历史）。

开始任何改动前：先读 `docs/architecture/super-agent.md`。它是唯一契约；代码、测试、提示词都以此为准。

## 命令

```
node --test "tests/*.test.ts"              # 全部测试（不要裸跑 node --test：会扫到 dsh/ 的 vitest spec）
node src/cli.ts run seed.config.json --once # 真实一轮（需 seed.env 凭证）
node src/cli.ts desktop seed.config.json [--no-browser] # 桌面控制台（默认 4780）
node src/cli.ts doctor seed.config.json     # 真实体检
node src/cli.ts panel seed.db [--json]      # 只列待人工项
```

## 不可违反的三条

1. **单向状态流**：状态只能由 `reduce(state, event)` 产生；唯一写入口 `store.append()`。禁止任何模块直接改聚合对象。
2. **单点收敛**：每类变更只有一个落点（见文档第 5 节）。同类逻辑出现两处即视为错误。
3. **可测试**：不引入需要网络的测试；时间只走 `clock.ts`；随机只走 `ids.ts`。

## 工程约定

- 零第三方依赖。要加依赖必须先和用户确认。
- 单文件 <= 210 行；超过就按职责拆分。
- 类型优先：用判别联合与 `const` 字面量，不用 `enum`（Node 类型擦除不支持）。
- 新事件 = `events.ts` 类型表 + `reducer.ts` 分支 + `tests/architecture.test.ts` 自动校验。
- 破坏性操作（删数据、改 schema、git reset）先确认。