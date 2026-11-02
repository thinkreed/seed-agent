/** Router Session 的提示词规则与客户端工厂（与状态机分离，便于复用/测试）。 */

import { OpenAIClient } from "./llm/openai.ts";
import type { ContextBudget } from "./context.ts";
import type { State } from "./domain.ts";
import type { ModelClient } from "./model.ts";

export interface RouterBatch {
  readonly threads: number;
  readonly triggers: number;
  readonly at: number;
}

export interface RouterSessionOptions {
  readonly client: ModelClient;
  readonly state: () => State;
  readonly budget?: ContextBudget;
  readonly maxSteps?: number;
  readonly historyMessages?: number;
  readonly memoryChars?: number;
  readonly clock?: import("./clock.ts").Clock;
  readonly onBatch?: (batch: RouterBatch) => void;
  /** Router 对话历史的落盘路径；缺省只保存在内存。 */
  readonly historyPath?: string;
}

export const ROUTER_ACCEPT_RULES = [
  "You are also the Router: one persistent context across all threads and channels.",
  "You receive every queued thread in one batch. Decide once per threadId.",
  'Output JSON only: {"decisions":[{"threadId","kind","strength","scope","reason","rules","reply"}]}.',
  "kind is accept | stop | ignore | unavailable | reply.",
  "Use reply when a person asks you directly or asks for status; put the short answer in reply (no ticket).",
  "Use ignore for chatter, thanks, status updates, and work already covered by a ticket.",
  "Use reply for direct questions/status asks; keep it short, IM-style.",
  "Use stop when a person ends work on the thread.",
  'If deciding needs context that is not inline, first output {"recall":[{"kind":"trigger|thread|ticket","id":"..."}]} and wait for the results.',
].join("\n");

export const ROUTER_CHAT_RULES = [
  "You are the Router talking to a person. Answer briefly and concretely (IM-style, <=100 words unless asked for detail).",
  'Output JSON only: {"reply":"...","work":"optional task text"}.',
  "Set work only when the person asks for real work; the host will open a ticket with that text.",
  "Never claim a ticket was opened unless work is set.",
].join("\n");

/** 信道定制的交互规范（文章 §4.2）：IM 低打扰，异步信道结构化。 */
export function channelChatRules(channel: "im" | "async"): string {
  if (channel === "async") {
    return [
      "Channel: asynchronous (GitHub / email / docs).",
      "Deliver structured content: conclusion first, then scope/changes/verification; information density over brevity.",
    ].join(" ");
  }
  return "Channel: instant messaging. Low-disturbance, plain text, <=100 words, no markdown.";
}

/** 用配置构造 OpenAI 兼容客户端的便捷工厂。 */
export function createRouterClient(options: {
  baseUrl: string;
  apiKey: string;
  model: string;
  timeoutMs: number;
}): ModelClient {
  return new OpenAIClient({
    baseUrl: options.baseUrl,
    apiKey: options.apiKey,
    model: options.model,
    timeoutMs: options.timeoutMs,
    temperature: 0,
    maxTokens: 1200,
  });
}