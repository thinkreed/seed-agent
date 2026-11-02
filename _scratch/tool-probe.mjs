import { mkdirSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'

for (const candidate of ['E:/projects/reed-dev/seed-agent/seed.env', 'seed.env']) {
  try {
    for (const line of readFileSync(candidate, 'utf8').split(/\r?\n/)) {
      const eq = line.indexOf('=')
      if (eq > 0 && line.slice(0, eq).trim() === 'BAILIAN_API_KEY') process.env.BAILIAN_API_KEY = line.slice(eq + 1).trim()
    }
  } catch {}
  if (process.env.BAILIAN_API_KEY) break
}

const root = mkdtempSync(join(tmpdir(), 'dsh-tool-probe-'))
const workspace = join(root, 'work')
const home = join(root, 'home')
mkdirSync(workspace, { recursive: true })
mkdirSync(home, { recursive: true })

const harness = new DeepSeekHarness({
  dshBin: 'E:/projects/reed-dev/seed-agent/dsh/apps/cli/lib/bin.js',
  dshHome: home,
  profile: 'sdk',
  patches: ['E:/projects/reed-dev/seed-agent/dsh/config/sdk-bailian.patch.yml'],
  cwd: workspace,
  provider: 'bailian',
  model: 'deepseek-v4.1-flash',
  env: { ...process.env, SUPER_AGENT_RECALL_INDEX: 'E:/projects/reed-dev/seed-agent/dsh/config/nonexistent.json' },
})
try {
  const result = await harness.run('列出你现在可用的全部工具名，只输出工具名，用逗号分隔，不要解释。')
  console.log('FINAL:', result.finalResponse)
} finally {
  await harness.close()
}