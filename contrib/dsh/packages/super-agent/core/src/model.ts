/** 模型端口：LLM 调用只需要实现这一个接口，测试用脚本替身。 */

export interface ModelMessage {
  readonly role: "system" | "user" | "assistant";
  readonly content: string;
}

export interface ModelClient {
  complete(messages: readonly ModelMessage[]): Promise<string>;
}