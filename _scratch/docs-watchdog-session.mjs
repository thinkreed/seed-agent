import { readFileSync, writeFileSync } from 'node:fs'

const auditPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-audit.md'
let audit = readFileSync(auditPath, 'utf8')
const marker = '\n\n## 2. 逐条差距（文章 §2–§6）'
const bullet = '> - 2026-11-01：**Watchdog 升级为独立 DSH session 裁定**——新增 `host/src/watchdog_session.ts`（`DshWatchdogJudge`）：确定性 findings 交给主系统之外的独立 DSH runtime 会话（独立工作目录 `<workspace>/.seed/watchdog`），由该会话输出 `{action, reason}`；`watchdogMode: "session"` 启用。证据：`WATCHDOG SESSION SMOKE OK`——`stalled:tk-000001` findings 由真实会话判为 ok（理由由模型生成），`.seed/watchdog` 目录创建，snapshot `action=ok`、interventions=1。'
if (!audit.includes('WATCHDOG SESSION SMOKE OK')) {
  audit = audit.replace(marker, `${bullet}\n${marker}`)
  writeFileSync(auditPath, audit, 'utf8')
}

const acceptancePath = 'E:/projects/reed-dev/seed-agent/docs/acceptance.md'
let acceptance = readFileSync(acceptancePath, 'utf8')
acceptance = acceptance.replace(
  '| 模型判断是否要介入 | `LlmWatchdogJudge` 注入 | `WATCHDOG LLM SMOKE OK`（确定性 intervene vs 模型判 benign ok） | ✅ |',
  '| 模型判断是否要介入 | `LlmWatchdogJudge`（内联）+ `DshWatchdogJudge`（独立 DSH session） | `WATCHDOG LLM SMOKE OK`；`WATCHDOG SESSION SMOKE OK`（独立会话判 ok、`.seed/watchdog` 工作目录、interventions=1） | ✅ |',
)
acceptance = acceptance.replace(
  '1. Watchdog 是 host 侧 judge call（非独立 DSH session）；链式召回覆盖 trigger/thread/ticket（无 Worker Session 节点/Correlation）；无 IM 静默检测；无 worker 后台时长上限；桌面仍是 dev 模式直到 P2-3；benchmark 是机制级。',
  '1. Watchdog 已有独立 DSH session 模式（`watchdogMode: "session"`），但仍不能自然语言询问或在线改主系统行为；链式召回覆盖 trigger/thread/ticket（无 Worker Session 节点/Correlation）；无 IM 静默检测；无 worker 后台时长上限；benchmark 是机制级。',
)
writeFileSync(acceptancePath, acceptance, 'utf8')

const variantPath = 'E:/projects/reed-dev/seed-agent/docs/dsh-variant.md'
let variant = readFileSync(variantPath, 'utf8')
const anchor = '- [x] **P2-2 §7 实验复现（机制级）**'
if (variant.includes(anchor) && !variant.includes('Watchdog 独立 DSH session')) {
  variant = variant.replace(anchor, '- [x] **Watchdog 独立 DSH session 模式**：`watchdogMode: "session"`，`WATCHDOG SESSION SMOKE OK`。\n' + anchor)
}
writeFileSync(variantPath, variant, 'utf8')
console.log('docs updated')