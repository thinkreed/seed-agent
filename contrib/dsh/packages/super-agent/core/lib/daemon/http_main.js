/**
 * HTTP daemon 进程入口（端侧执行环境）：
 *   SA_DAEMON_ROOT / SA_DAEMON_TOKEN / SA_DAEMON_PORT / SA_DAEMON_HOST
 */
import { SystemClock } from "../clock.js";
import { startHttpDaemon } from "./http.js";
const port = Number(process.env.SA_DAEMON_PORT ?? 0);
const daemon = await startHttpDaemon({
    root: process.env.SA_DAEMON_ROOT ?? process.cwd(),
    clock: new SystemClock(),
    ...(process.env.SA_DAEMON_TOKEN ? { token: process.env.SA_DAEMON_TOKEN } : {}),
    ...(process.env.SA_DAEMON_HOST ? { host: process.env.SA_DAEMON_HOST } : {}),
    port,
});
process.stdout.write(`${JSON.stringify({ ok: true, port: daemon.port })}\n`);
const shutdown = () => {
    void daemon.close().then(() => process.exit(0));
};
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
//# sourceMappingURL=http_main.js.map