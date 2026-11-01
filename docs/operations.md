# 运维手册（真实运行）

面向"在自己的机器上把 Super-agent 跑起来"的操作步骤。所有命令都在 `seed-agent/` 目录下执行。

## 1. 前置条件

| 依赖 | 检查命令 | 说明 |
|---|---|---|
| Node.js ≥ 22.18 | `node --version` | 自带 TS 类型擦除与 `node:sqlite` |
| 模型凭证 | `node src/cli.ts doctor seed.config.json` | `DEEPSEEK_API_KEY` 或其它 OpenAI 兼容端点 |
| GitHub | `gh auth status` | 需要 `repo` 权限；`gh auth login` 一次即可 |
| 飞书（可选） | 同上 doctor | 企业自建应用，`im:message` 权限 |

## 2. 凭证

在工作目录创建 `seed.env`（已在 `.gitignore`，不会入库）：

```dotenv
DEEPSEEK_API_KEY=sk-...
# 飞书（需要 IM 时）
FEISHU_APP_ID=cli_...
FEISHU_APP_SECRET=...
```

`App` 启动时会自动读取当前目录 `.env`，也可用 `SEED_ENV_FILE` 指定其它路径。**已存在的系统环境变量优先，不会被覆盖。**

## 3. 配置

```bash
cp seed.config.example.json seed.config.json
```

关键字段：

| 字段 | 作用 |
|---|---|
| `model` | `baseUrl` / `apiKeyEnv` / `name`（OpenAI 兼容） |
| `workRoot` | 每个工单的执行目录根 |
| `dbPath` | 事件库（SQLite），包含全部状态 |
| `sources.local.inbox` | JSONL 收件箱（每行一个 Trigger） |
| `sources.github` | 仓库与 reason 过滤（可留空表示全部） |
| `sources.feishu` | 应用凭证的环境变量名 + 群 `chat_ids` |
| `slots` / `intervalMs` / `staleSeconds` | 并发、轮询间隔、Watchdog 停滞阈值 |

## 4. 体检与运行

```bash
node src/cli.ts doctor seed.config.json        # 只读体检：凭证/端点/gh/飞书/文件系统
node src/cli.ts run seed.config.json --once    # 跑一轮真实链路后退出
node src/cli.ts run seed.config.json           # 常驻（Ctrl+C 优雅退出）
node src/cli.ts panel seed.db                  # 只列"谁在等我"
node src/cli.ts panel seed.db --json           # 机器可读
```

本地验证最小闭环：往 `inbox.jsonl` 追加一行

```json
{"id":"trg-1","source":"local","actor":"you","text":"在工单目录里写 hello.txt","threadIds":["local:1"],"channelIds":["local:1"]}
```

然后 `run --once`：模型会受理 → 建工单 → 拉起 worker 进程 → worker 用文件工具写文件 → 回报 → Router 输出回复到 stdout。

## 5. 数据与恢复

- 状态全在 `dbPath`（SQLite）：`events`（append-only）、`outbox`（stored work）、`cursors`（Source 位点）。
- 备份：直接复制 `seed.db`（WAL 模式建议先停进程或用 `.backup`）。
- 崩溃恢复：重启后 `run` 会调用 `recoverAfterRestart()`，把 running 的 assignment 收口并留下 `resume` 注记。
- 重放：`node -e "import('./src/store.ts').then(m=>{const s=new m.SqliteStore('seed.db');console.log(s.replayHash())})"` 可校验状态一致性。

## 6. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `missing env DEEPSEEK_API_KEY` | 凭证没进进程环境 | 检查 `seed.env` 或系统环境变量 |
| `model request failed: HTTP 401` | key 无效/过期 | 更新 key |
| `gh auth failed` | 未登录或 token 失效 | `gh auth login` |
| 工单停在 `working/queued` | worker 启动失败 | 看 worker stderr、检查 `workRoot` 权限 |
| 报告迟迟不回来 | 模型超时/worker 崩溃 | Watchdog 会在 `staleSeconds` 后判停滞并重试 |
| 飞书 `code 99991663` | app_id/secret 或权限问题 | 检查应用凭证与 `im:message` 权限 |

## 7. 常驻部署

Windows 计划任务（登录时启动）：

```powershell
schtasks /create /tn "seed-superagent" /tr "node E:\projects\reed-dev\seed-agent\src\cli.ts run E:\projects\reed-dev\seed-agent\seed.config.json" /sc onlogon
```

Linux systemd：

```ini
[Unit]
Description=seed-superagent
After=network-online.target

[Service]
WorkingDirectory=/opt/seed-agent
EnvironmentFile=/opt/seed-agent/seed.env
ExecStart=/usr/bin/node src/cli.ts run seed.config.json
Restart=always

[Install]
WantedBy=multi-user.target
```

## 8. 验收脚本

`ash
node scripts/live_watchdog.ts   # 真机：卡死 worker -> 模型判定 -> 重试（需 seed.env 模型 key）
`
