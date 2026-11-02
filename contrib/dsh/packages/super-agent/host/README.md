# @deepseek-ai/dsh-super-agent-host

把 Super-agent 内核挂成 cordis 服务（`superAgent`），供 DSH 宿主与 client 插件使用。

- `ingest(trigger)` / `tick()` / `state()` / `tickets()` / `ticket(id)`
- `retry` / `reply` / `pause` / `resume`
- 生命周期：`ctx.effect` 关闭时自动关库

M2 占位：`PendingDshExecutor`（只记录派工）与 `explicitAssessor`（Gate 已放行则接受）。
M3 会替换为 DSH session 执行器与 DSH LLM 评估。

```ts
import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '@deepseek-ai/dsh-super-agent-host'

const ctx = new Context()
await ctx.plugin(SuperAgentHost, { dbPath: '.seed/super-agent.db', slots: 2 })
ctx.superAgent.ingest({ id: 'trg-1', source: 'local', actor: 'me', text: 'hi', threadIds: ['local:1'], channelIds: ['local:1'], at: Date.now() / 1000 })
await ctx.superAgent.tick()
console.log(ctx.superAgent.tickets())
```
## 执行器

- 配置了 dshBin + dshHome 时用 SdkDshExecutor：DeepSeekHarness.run(prompt) 拉起真实 DSH runtime（模型/工具/沙箱），回合结束把 finalResponse 作为 Report.summary 写回引擎；同工单后续投递复用 sessionId。
- 否则用 PendingDshExecutor（只记录派工，便于无 DSH 环境的单测）。
- dshBin 指向 fork 的 CLI 产物：dsh/apps/cli/lib/bin.js。
