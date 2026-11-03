/**
 * daemon 进程入口：只做执行，不持有会话状态。
 *
 *   node src/daemon/main.ts
 *
 * 环境变量：
 *   SEED_DAEMON_ROOT  执行根目录（每个工单一个子目录）
 *   SEED_DAEMON_ENV   额外环境变量（JSON 对象，透传给 worker）
 */
export {};
