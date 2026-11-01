import { readFileSync, writeFileSync } from 'node:fs'

const path = 'E:/projects/reed-dev/seed-agent/contrib/dsh/config/sdk-bailian.patch.yml'
let text = readFileSync(path, 'utf8')
// 去掉旧的顶层行/旧 insert 块，统一重写为带占位符的 root insert。
text = text.replace(/\n- id: super-agent-tool-recall\r?\n  name: '[^']+'\r?\n?/g, '\n')
text = text.replace(/\n- insert:\r?\n    - id: super-agent-tool-recall\r?\n      name: '[^']+'\r?\n?/g, '\n')
const block = "\n- insert:\n    - id: super-agent-tool-recall\n      name: '__SUPER_AGENT_RECALL_TOOL__'\n"
text = text.trimEnd() + block
writeFileSync(path, text, 'utf8')
console.log(text.split(/\r?\n/).slice(-6).join('\n'))