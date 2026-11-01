/**
 * 多信道交付真机：同一条报告分别按 IM（飞书，≤100 字）与 GitHub（结构化）发送。
 * 需要 FEISHU_APP_ID/SECRET 与 gh 登录；输出两条 message id。
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { ChannelFormattingWriter, MultiChannelWriter } from '../lib/index.js'

for (const candidate of ['../seed.env', '../../seed.env', 'seed.env', '../../../seed.env']) {
  const path = resolve(candidate)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = /^(FEISHU_APP_ID|FEISHU_APP_SECRET)=(.+)$/.exec(line)
    if (match) process.env[match[1]] = match[2].trim()
  }
  if (process.env.FEISHU_APP_ID) break
}

const chatId = process.argv[2] ?? 'oc_93f1a464c8258f572ff133db799a2546'
const ghTarget = process.argv[3] ?? 'gh:thinkreed/seed-agent-e2e#3'
const appId = process.env.FEISHU_APP_ID?.trim()
const appSecret = process.env.FEISHU_APP_SECRET?.trim()
if (!appId || !appSecret) throw new Error('feishu credentials missing')

const inner = new MultiChannelWriter({ feishu: { appId, appSecret }, log: (line) => console.log(line) })
const writer = new ChannelFormattingWriter(inner)
const long = '## 完成\n\n已完成渠道格式联调：IM 侧压缩到 100 字以内，GitHub 侧用结构化标题与结论段交付。**结论：通道格式规范生效**，细节见仓库。'
await writer.send({ id: 'fmt-im', threadId: 'local:fmt', address: chatId }, long)
await writer.send({ id: 'fmt-gh', threadId: 'local:fmt', address: ghTarget }, long)
const sent = inner.history
console.log('sent:', JSON.stringify(sent))
const ok = sent.length === 2 && sent.some((item) => item.address === chatId) && sent.some((item) => item.address === ghTarget)
console.log(ok ? 'CHANNEL FORMAT LIVE OK' : 'CHANNEL FORMAT LIVE FAIL')
process.exit(ok ? 0 : 1)