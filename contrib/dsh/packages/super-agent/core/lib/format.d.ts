/**
 * 多信道交付规范（文章 §4.2）：
 * - IM：低打扰、短（≤100 字）、去 Markdown；
 * - GitHub / 邮件 / 文档：结构化、高信息密度；
 * 渠道适配器只负责投递，格式化在唯一入口完成。
 */
/** 把任意报告文本压成 IM 能接受的短消息：去 Markdown、取首句、截断。 */
export declare function compactForIm(text: string, limit?: number): string;
/** GitHub/邮件/文档等异步信道：结构化交付。 */
export declare function structureForAsync(text: string): string;
/** 按地址选择交付格式。 */
export declare function formatForChannel(address: string, text: string): string;
