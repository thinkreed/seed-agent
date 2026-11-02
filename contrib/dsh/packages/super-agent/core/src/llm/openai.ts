/**
 * OpenAI 兼容客户端（DeepSeek / 百炼 / 任何 /chat/completions 兼容端点）。
 * 真实 HTTP，无 mock 分支；超时、限流重试都在这里。
 */

import type { ModelClient, ModelMessage } from "../model.ts";

export interface OpenAIClientOptions {
  readonly baseUrl: string;
  readonly apiKey: string;
  readonly model: string;
  readonly temperature?: number;
  readonly timeoutMs?: number;
  readonly maxRetries?: number;
  readonly maxTokens?: number;
}

interface ChatCompletionResponse {
  readonly choices?: readonly { readonly message?: { readonly content?: string | null } }[];
  readonly error?: { readonly message?: string };
}

export class OpenAIClient implements ModelClient {
  private readonly options: OpenAIClientOptions;

  constructor(options: OpenAIClientOptions) {
    this.options = options;
  }

  async complete(messages: readonly ModelMessage[]): Promise<string> {
    const url = `${this.options.baseUrl.replace(/\/$/, "")}/chat/completions`;
    const body = JSON.stringify({
      model: this.options.model,
      messages,
      temperature: this.options.temperature ?? 0,
      ...(this.options.maxTokens === undefined ? {} : { max_tokens: this.options.maxTokens }),
    });
    const attempts = (this.options.maxRetries ?? 2) + 1;
    let lastError = "unknown error";
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const result = await this.once(url, body);
      if (result.ok) return result.content;
      lastError = result.error;
      if (!result.retryable || attempt + 1 >= attempts) break;
      await sleep(result.retryAfterMs ?? 500 * (attempt + 1));
    }
    throw new Error(`model request failed: ${lastError}`);
  }

  private async once(
    url: string,
    body: string,
  ): Promise<{ ok: true; content: string } | { ok: false; error: string; retryable: boolean; retryAfterMs?: number }> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 120_000);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.options.apiKey}`,
        },
        body,
        signal: controller.signal,
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        const retryable = response.status === 429 || response.status >= 500;
        const retryAfterMs = retryAfter(response.headers.get("retry-after"));
        return {
          ok: false,
          error: `HTTP ${response.status}: ${redact(text).slice(0, 300)}`,
          retryable,
          ...(retryAfterMs === undefined ? {} : { retryAfterMs }),
        };
      }
      const payload = (await response.json()) as ChatCompletionResponse;
      const content = payload.choices?.[0]?.message?.content;
      if (typeof content !== "string") {
        return { ok: false, error: "response has no message content", retryable: false };
      }
      return { ok: true, content };
    } catch (error) {
      return { ok: false, error: redact(String(error)), retryable: true };
    } finally {
      clearTimeout(timer);
    }
  }
}

/** 错误信息里常见的 key/token 不能进入日志。 */
function redact(value: string): string {
  return value
    .replace(/\bsk-[A-Za-z0-9._-]{4,}\b/g, "sk-***")
    .replace(/\bBearer\s+[A-Za-z0-9._-]{4,}\b/gi, "Bearer ***");
}

function retryAfter(header: string | null): number | undefined {
  if (!header) return undefined;
  const seconds = Number(header);
  return Number.isFinite(seconds) ? seconds * 1000 : undefined;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}