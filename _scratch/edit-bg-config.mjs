import { readFileSync, writeFileSync } from 'node:fs'

const path = 'E:/projects/reed-dev/seed-agent/contrib/dsh/config/sdk-bailian.patch.yml'
let text = readFileSync(path, 'utf8')
if (!text.includes('super-agent-tool-background')) {
  text = `${text.trimEnd()}\n- insert:\n    - id: super-agent-tool-background\n      name: '__SUPER_AGENT_BACKGROUND_TOOL__'\n`
}
writeFileSync(path, text, 'utf8')
console.log(text.split(/\r?\n/).slice(-5).join('\n'))