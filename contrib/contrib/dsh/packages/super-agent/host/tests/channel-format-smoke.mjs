/** 多信道交付规范：IM 压缩、GitHub 结构化、写手按地址分派。 */
import { ChannelFormattingWriter, compactForIm, formatForChannel, structureForAsync } from '../lib/index.js'

const long = '## 完成\n\n已完成工单（tk-000001）：在 [工单目录](C:/tmp/work) 新建了 `report.md`，写入并回读校验一致。**结论：成功**。这次任务包含了很多额外细节，包括原因分析、验证步骤、产物位置说明，以及给后续维护者的建议。'
const compact = compactForIm(long)
const structured = structureForAsync(long)
console.log('im:', JSON.stringify(compact))
console.log('im length:', compact.length)
console.log('gh head:', JSON.stringify(structured.split('\n').slice(0, 8)))

const sent = []
const writer = new ChannelFormattingWriter({ send: async (channel, text) => { sent.push({ address: channel.address, text }) } })
await writer.send({ id: 'c1', threadId: 't1', address: 'oc_chat' }, long)
await writer.send({ id: 'c2', threadId: 't2', address: 'gh:owner/repo#12' }, long)
console.log('sent:', JSON.stringify(sent.map((item) => ({ address: item.address, length: item.text.length, head: item.text.slice(0, 30) }))))

const ok = Boolean(
  compact.length <= 110 && !compact.includes('](') && compact.endsWith('…') &&
  structured.startsWith('## Super-agent 更新') && structured.includes('### 结论') &&
  sent[0].text.length <= 110 && sent[1].text.startsWith('## Super-agent 更新') &&
  formatForChannel('oc_x', 'hi') === 'hi',
)
console.log(ok ? 'CHANNEL FORMAT SMOKE OK' : 'CHANNEL FORMAT SMOKE FAIL')
process.exit(ok ? 0 : 1)