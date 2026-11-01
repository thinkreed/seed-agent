import { mkdtempSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const m = await import('file:///E:/projects/reed-dev/seed-agent/dsh/packages/super-agent/tool-background/lib/index.js')
const defs = new Map()
m.apply({ tools: { register: (d) => defs.set(d.name, d) } })
const dir = mkdtempSync(join(tmpdir(), 'bg-test-'))
process.chdir(dir)
const start = defs.get('super_agent_start')
const status = defs.get('super_agent_status')
const r = await start.execute({ command: 'Start-Sleep -Seconds 2; Set-Content async-done.txt done' }, {})
console.log('start:', JSON.stringify(r))
await new Promise((w) => setTimeout(w, 1000))
console.log('mid:', JSON.stringify(await status.execute({ jobId: r.jobId }, {})))
await new Promise((w) => setTimeout(w, 2500))
console.log('end:', JSON.stringify(await status.execute({ jobId: r.jobId }, {})))
console.log('file:', existsSync(join(dir, 'async-done.txt')))
