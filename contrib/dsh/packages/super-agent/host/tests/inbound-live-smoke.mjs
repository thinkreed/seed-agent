/**
 * 入站 Source 真机连通性：飞书消息列表 + GitHub 通知（只读，不产生工单）。
 * 需要 FEISHU_APP_ID/SECRET 与 gh 登录；任一调用失败即 FAIL。
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { FeishuHttpClient, FeishuSource, GhCliClient } from '../lib/index.js'

for (const candidate of ['../seed.env', '../../seed.env', 'seed.env', '../../../seed.env']) {
  const path = resolve(candidate)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = /^([A-Z_]+)=(.+)$/.exec(line)
    if (match && ['FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_CHAT_ID'].includes(match[1])) {
      process.env[match[1]] = match[2].trim()
    }
  }
  if (process.env.FEISHU_APP_ID) break
}

const chatIds = (process.env.SA_FEISHU_CHAT_IDS ?? process.env.FEISHU_CHAT_ID ?? '').split(',').map((v) => v.trim()).filter(Boolean)
if (chatIds.length === 0) {
  chatIds.push('oc_93f1a464c8258f572ff133db799a2546')
}

let failures = 0
let feishuCount = 0
if (process.env.FEISHU_APP_ID && process.env.FEISHU_APP_SECRET) {
  const client = new FeishuHttpClient({ appId: process.env.FEISHU_APP_ID, appSecret: process.env.FEISHU_APP_SECRET, chatIds })
  const source = new FeishuSource(client, { sinceSeconds: 86_400 })
  try {
    const messages = await client.listMessages()
    const triggers = await source.poll()
    feishuCount = messages.length
    console.log('feishu messages(24h):', messages.length, 'triggers:', triggers.length)
    console.log('feishu sample:', messages.slice(-2).map((message) => `${message.chatId}/${message.sender}: ${message.text.slice(0, 40)}`).join(' | '))
    if (messages.length > 0 && triggers.length === 0) {
      console.log('note: messages exist but none are human recent messages (bot/self filtered)')
    }
  } catch (error) {
    failures += 1
    console.log('feishu FAIL:', String(error))
  }
} else {
  console.log('feishu skipped (no credentials)')
}

try {
  const gh = new GhCliClient({ excludeSelf: true })
  const notifications = await gh.listNotifications()
  console.log('github notifications:', notifications.length)
  console.log('github sample:', notifications.slice(0, 2).map((item) => `${item.repo}#${item.number} ${item.reason}`).join(' | '))
} catch (error) {
  failures += 1
  console.log('github FAIL:', String(error))
}

console.log(failures === 0 ? 'INBOUND LIVE OK' : 'INBOUND LIVE FAIL')
process.exit(failures === 0 ? 0 : 1)