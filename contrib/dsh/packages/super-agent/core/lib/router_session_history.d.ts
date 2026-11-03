/** Router 对话历史的轻量落盘：跨进程重启保留最近对话，不是业务状态。 */
import type { ModelMessage } from "./model.ts";
export declare function loadChatHistory(path: string | undefined): ModelMessage[];
export declare function saveChatHistory(path: string | undefined, messages: readonly ModelMessage[]): void;
