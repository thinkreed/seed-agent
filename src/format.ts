/**
 * 多信道交付规范（文章 §4.2）：
 * - IM：低打扰、短（≤100 字）、去 Markdown；
 * - GitHub / 邮件 / 文档：结构化、高信息密度；
 * 渠道适配器只负责投递，格式化在唯一入口完成。
 */

const IM_LIMIT = 100;

const ASYNC_PREFIXES = ["gh:", "mailto:", "email:", "docs:"] as const;

/** 把任意报告文本压成 IM 能接受的短消息：去 Markdown、取首句、截断。 */
export function compactForIm(text: string, limit = IM_LIMIT): string {
  const plain = text
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[`*_>#-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (plain.length <= limit) return plain;
  const head = plain.slice(0, limit);
  const cut = Math.max(head.lastIndexOf("。"), head.lastIndexOf("；"), head.lastIndexOf(". "), head.lastIndexOf("，"));
  const bounded = cut > limit * 0.5 ? head.slice(0, cut + 1) : head;
  return `${bounded.trim()}…`;
}

/** GitHub/邮件/文档等异步信道：结构化交付。 */
export function structureForAsync(text: string): string {
  const body = text.trim();
  return [
    "## Super-agent 更新",
    "",
    "### 结论",
    "",
    body,
    "",
    "---",
    "_由 seed-agent Super-agent 自动更新；具体改动以仓库/工单目录为准。_",
  ].join("\n");
}

/** 按地址选择交付格式。 */
export function formatForChannel(address: string, text: string): string {
  if (ASYNC_PREFIXES.some((prefix) => address.startsWith(prefix))) return structureForAsync(text);
  return compactForIm(text);
}