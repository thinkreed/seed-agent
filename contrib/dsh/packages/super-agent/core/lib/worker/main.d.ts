/**
 * Worker 进程入口（真实执行会话）。
 *
 * 环境变量：
 *   SEED_WORKER_ROOT          工单目录（工作区根）
 *   SEED_WORKER_TICKET        工单 ID
 *   SEED_WORKER_SHORT_NAME    工单短名
 *   SEED_WORKER_SCOPE         授权范围
 *   SEED_WORKER_INPUT         初始输入的 JSON（Trigger 数组）
 *   SEED_MODEL_BASE_URL       模型端点（OpenAI 兼容）
 *   SEED_MODEL_API_KEY        模型密钥
 *   SEED_MODEL_NAME           模型名
 *   SEED_WORKER_MAX_STEPS     每轮最多几步（默认 12）
 *
 * stdin：逐行 JSON，形如 {"inputId","kind","ref"}，代表 daemon 投递的新输入。
 * stdout：逐行 JSON 报告 {"type":"report","status","summary"}。
 */
export {};
