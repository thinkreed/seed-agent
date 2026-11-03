/**
 * daemon 进程入口：只做执行，不持有会话状态。
 *
 *   node src/daemon/main.ts
 *
 * 环境变量：
 *   SEED_DAEMON_ROOT  执行根目录（每个工单一个子目录）
 *   SEED_DAEMON_ENV   额外环境变量（JSON 对象，透传给 worker）
 */
import { createInterface } from "node:readline";
import { SystemClock } from "../clock.js";
import { DaemonAgent } from "./agent.js";
function parseEnv(raw) {
    if (!raw)
        return {};
    try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            return Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, String(value)]));
        }
    }
    catch {
        return {};
    }
    return {};
}
process.on("uncaughtException", (error) => {
    process.stderr.write(`daemon uncaught: ${String(error?.stack ?? error)}\n`);
});
process.on("unhandledRejection", (reason) => {
    process.stderr.write(`daemon unhandled rejection: ${String(reason)}\n`);
});
const agent = new DaemonAgent({
    clock: new SystemClock(),
    root: process.env.SEED_DAEMON_ROOT ?? ".",
    env: parseEnv(process.env.SEED_DAEMON_ENV),
    emit: (event) => process.stdout.write(`${JSON.stringify(event)}\n`),
});
createInterface({ input: process.stdin }).on("line", (line) => {
    const raw = line.trim();
    if (!raw)
        return;
    void (async () => {
        let request;
        try {
            request = JSON.parse(raw);
        }
        catch {
            return;
        }
        const response = await agent.handle(request);
        process.stdout.write(`${JSON.stringify(response)}\n`);
    })();
});
//# sourceMappingURL=main.js.map