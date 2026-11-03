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
import { createInterface } from "node:readline";
import { readFileSync } from "node:fs";
import { SystemClock } from "../clock.js";
import { JobRegistry } from "../jobs.js";
import { OpenAIClient } from "../llm/openai.js";
import { ReactLoop } from "../react.js";
import { subagentTool } from "../subagent_tool.js";
import { fileTools } from "../tools/files.js";
import { shellTool } from "../tools/shell.js";
function env(name, fallback = "") {
    return process.env[name] ?? fallback;
}
function required(name) {
    const value = env(name);
    if (!value) {
        process.stderr.write(`missing env: ${name}\n`);
        process.exit(2);
    }
    return value;
}
function parseInputs(raw) {
    if (!raw)
        return [];
    try {
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed))
            return [];
        return parsed.filter((item) => typeof item === "object" && item !== null);
    }
    catch {
        return [];
    }
}
const root = required("SEED_WORKER_ROOT");
const ticket = {
    id: env("SEED_WORKER_TICKET", "tk-local"),
    shortName: env("SEED_WORKER_SHORT_NAME", "t-local"),
    mandate: {
        policyVersion: "",
        strength: "explicit",
        scope: env("SEED_WORKER_SCOPE", "ticket"),
        source: "worker",
        actor: "",
        rules: [],
        triggerId: "",
    },
    threadIds: [],
    channelIds: [],
    state: "open",
    stopped: false,
    createdAt: 0,
};
const clock = new SystemClock();
const jobs = new JobRegistry(clock, { maxRunSeconds: 1800 });
const model = new OpenAIClient({
    baseUrl: required("SEED_MODEL_BASE_URL"),
    apiKey: required("SEED_MODEL_API_KEY"),
    model: required("SEED_MODEL_NAME"),
});
const baseTools = {
    ...fileTools(root),
    run_shell: shellTool({ root }),
    ...(env("SEED_RECALL_INDEX")
        ? {
            recall: {
                description: "Read a trigger/thread/ticket by id for chained recall (kind, id).",
                async run(args) {
                    const data = JSON.parse(readFileSync(required("SEED_RECALL_INDEX"), "utf8"));
                    const kind = String(args.kind ?? "trigger");
                    const id = String(args.id ?? "");
                    const section = data[kind];
                    if (!section)
                        throw new Error(`unknown recall kind: ${kind}`);
                    const item = section[id];
                    if (!item)
                        throw new Error(`unknown ${kind}: ${id}`);
                    return item;
                },
            },
        }
        : {}),
};
const tools = {
    ...baseTools,
    spawn_subagent: subagentTool({ model, tools: baseTools, jobs, clock, ticket }),
};
const descriptions = {
    read_file: "Read a text file inside the workspace (path, optional start/count not needed).",
    write_file: "Create or overwrite a text file inside the workspace (path, content).",
    edit_file: "Replace exact text in a file (path, old, new, optional all=true).",
    list_files: "List entries of a directory inside the workspace (path).",
    run_shell: "Run one shell command in the workspace (command). Prefer start() for long commands.",
    recall: "Read a trigger/thread/ticket by id for chained recall (kind, id).",
    spawn_subagent: "Run a focused subtask in an isolated subagent context (task); returns {status, summary}.",
};
for (const [name, tool] of Object.entries(tools)) {
    tool.description = descriptions[name] ?? "";
}
const loop = new ReactLoop({
    model,
    tools,
    jobs,
    clock,
    maxSteps: Number(env("SEED_WORKER_MAX_STEPS", "12")),
    nextInputs: () => inbox.splice(0, inbox.length).map((item) => item.text),
});
function emit(status, summary) {
    process.stdout.write(`${JSON.stringify({ type: "report", status, summary })}\n`);
}
const inbox = parseInputs(env("SEED_WORKER_INPUT"));
let running = false;
let closed = false;
async function kick() {
    if (running)
        return;
    running = true;
    while (inbox.length > 0) {
        const batch = inbox.splice(0, inbox.length);
        const report = await loop.run(ticket, batch);
        emit(report.status, report.summary);
        if (report.status !== "progress" && report.status !== "waiting")
            break;
    }
    running = false;
    if (closed && inbox.length === 0)
        process.exit(0);
}
createInterface({ input: process.stdin }).on("line", (line) => {
    const raw = line.trim();
    if (!raw)
        return;
    try {
        const payload = JSON.parse(raw);
        inbox.push({
            id: payload.inputId ?? `inp-${inbox.length}`,
            source: "worker",
            actor: "router",
            text: payload.ref ?? "",
            threadIds: [],
            channelIds: [],
            at: clock.now(),
        });
    }
    catch {
        return;
    }
    void kick();
});
process.stdin.on("close", () => {
    closed = true;
    if (!running)
        void kick();
});
if (inbox.length > 0)
    void kick();
//# sourceMappingURL=main.js.map