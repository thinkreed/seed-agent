/**
 * 多信道交付规范（文章 §4.2）：
 * - IM：低打扰、短（≤100 字），只在决策/验收类消息上发；去掉 Markdown 噪音。
 * - GitHub / 异步信道：结构化交付（标题、结论、范围、落款），信息密度优先。
 */
import type { Channel, ChannelWriter } from '@deepseek-ai/dsh-super-agent-core'

const IM_LIMIT = 100

/** 把任意报告文本压成 IM 能接受的短消息：去 Markdown、取首句、截断。 */
export function compactForIm(text: string, limit = IM_LIMIT): string {
  const plain = text
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[`*_>#-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (plain.length <= limit) return plain
  const head = plain.slice(0, limit)
  const cut = Math.max(head.lastIndexOf('。'), head.lastIndexOf('；'), head.lastIndexOf('. '), head.lastIndexOf('，'))
  const bounded = cut > limit * 0.5 ? head.slice(0, cut + 1) : head
  return `${bounded.trim()}…`
}

/** GitHub/邮件等异步信道：结构化交付。 */
export function structureForAsync(text: string): string {
  const body = text.trim()
  return [
    '## Super-agent 更新',
    '',
    '### 结论',
    '',
    body,
    '',
    '---',
    '_由 seed-agent Super-agent 自动更新；具体改动以仓库/工单目录为准。_',
  ].join('\n')
}

/** 按地址选择交付格式（gh/docs/mail 走结构化，其余按 IM 压缩）。 */
export function formatForChannel(address: string, text: string): string {
  if (/^(gh:|docs:|mailto:|email:)/.test(address)) return structureForAsync(text)
  return compactForIm(text)
}

/** 包一层 ChannelWriter：所有出站消息按信道规范格式化。 */
export class ChannelFormattingWriter implements ChannelWriter {
  private readonly inner: ChannelWriter

  constructor(inner: ChannelWriter) {
    this.inner = inner
  }

  async send(channel: Channel, text: string): Promise<void> {
    await this.inner.send(channel, formatForChannel(channel.address || channel.id, text))
  }
}