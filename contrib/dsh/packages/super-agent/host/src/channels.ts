/**
 * 出站渠道：把 Router 排队的回复真正发出去。
 *
 * 地址约定：
 * - `gh:owner/repo#123` → `gh issue comment`（GitHub）
 * - `oc_...` / `feishu:oc_...` → 飞书群消息（tenant_access_token + im/v1/messages）
 * - 其它 → 本地日志（控制台/事件流可见）
 */

import { spawn } from 'node:child_process'
import type { Channel, ChannelWriter } from '@deepseek-ai/dsh-super-agent-core'

export interface FeishuChannelSettings {
  readonly appId: string
  readonly appSecret: string
  readonly baseUrl?: string
}

export interface ChannelSettings {
  readonly feishu?: FeishuChannelSettings
  readonly log?: (line: string) => void
}

export interface SentChannelMessage {
  readonly address: string
  readonly messageId: string
  readonly at: number
}

const DEFAULT_FEISHU_BASE = 'https://open.feishu.cn/open-apis'

export class MultiChannelWriter implements ChannelWriter {
  private readonly settings: ChannelSettings
  private token: { readonly value: string; readonly expiresAt: number } | undefined
  private readonly sent: SentChannelMessage[] = []

  constructor(settings: ChannelSettings) {
    this.settings = settings
  }

  /** 最近发出的消息（工作台/验收用）。 */
  get history(): readonly SentChannelMessage[] {
    return this.sent
  }

  async send(channel: Channel, text: string): Promise<void> {
    const address = (channel.address || channel.id).trim()
    if (address.startsWith('gh:')) {
      const messageId = await this.sendGithub(address.slice(3), text)
      this.record(address, messageId)
      return
    }
    const feishuChat = address.startsWith('feishu:') ? address.slice(7) : address
    if (this.settings.feishu && feishuChat.startsWith('oc_')) {
      const messageId = await this.sendFeishu(feishuChat, text)
      this.record(address, messageId)
      return
    }
    this.settings.log?.(`[channel ${address}] ${text}`)
    this.record(address, `local-${this.sent.length + 1}`)
  }

  private record(address: string, messageId: string): void {
    this.sent.push({ address, messageId, at: Math.floor(Date.now() / 1000) })
    if (this.sent.length > 20) this.sent.shift()
  }

  private async tenantToken(): Promise<string> {
    const feishu = this.settings.feishu
    if (!feishu) throw new Error('feishu channel not configured')
    const now = Date.now()
    if (this.token && this.token.expiresAt > now + 60_000) return this.token.value
    const base = feishu.baseUrl ?? DEFAULT_FEISHU_BASE
    const response = await fetch(`${base}/auth/v3/tenant_access_token/internal`, {
      method: 'POST',
      headers: { 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ app_id: feishu.appId, app_secret: feishu.appSecret }),
    })
    const payload = (await response.json()) as { code?: number; msg?: string; tenant_access_token?: string; expire?: number }
    if (!response.ok || payload.code !== 0 || !payload.tenant_access_token) {
      throw new Error(`feishu token failed: ${String(payload.code)} ${payload.msg ?? response.status}`)
    }
    this.token = { value: payload.tenant_access_token, expiresAt: now + (payload.expire ?? 7200) * 1000 }
    return payload.tenant_access_token
  }

  private async sendFeishu(chatId: string, text: string): Promise<string> {
    const token = await this.tenantToken()
    const base = this.settings.feishu?.baseUrl ?? DEFAULT_FEISHU_BASE
    const response = await fetch(`${base}/im/v1/messages?receive_id_type=chat_id`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ receive_id: chatId, msg_type: 'text', content: JSON.stringify({ text }) }),
    })
    const payload = (await response.json()) as { code?: number; msg?: string; data?: { message_id?: string } }
    if (!response.ok || payload.code !== 0) {
      throw new Error(`feishu send failed: ${String(payload.code)} ${payload.msg ?? response.status}`)
    }
    return payload.data?.message_id ?? 'unknown'
  }

  private async sendGithub(target: string, text: string): Promise<string> {
    const match = /^([^#]+)#(\d+)$/.exec(target)
    if (!match) throw new Error(`github channel needs owner/repo#number, got ${target}`)
    const [, repo, number] = match
    await new Promise<void>((resolvePromise, reject) => {
      const child = spawn('gh', ['issue', 'comment', String(number), '--repo', String(repo), '--body', text], { stdio: 'ignore' })
      child.once('error', reject)
      child.once('exit', (code) => {
        if (code === 0) resolvePromise()
        else reject(new Error(`gh exited ${String(code)}`))
      })
    })
    return `gh-${String(repo)}-${String(number)}`
  }
}