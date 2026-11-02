/**
 * Router Session 已下沉到 core：`src/router_session.ts`（内核与 host 共用同一实现）。
 * 这里只做转发，避免同一套批处理/记忆/对话逻辑在两处维护。
 */

export {
  RouterSession,
  createRouterClient,
  type RouterBatch,
  type RouterSessionOptions,
} from '@deepseek-ai/dsh-super-agent-core'