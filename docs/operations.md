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
BAILIAN_API_KEY=sk-...
BAILIAN_BASE_URL=https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1
# 飞书（需要 IM 时）
FEISHU_APP_ID=cli_...
FEISHU_APP_SECRET=...
```

百炼配置已内置为 [config/bailian.patch.yml](config/bailian.patch.yml)（provider `bailian`、模型 `deepseek-v4.1-flash`、`apiKeyEnv=BAILIAN_API_KEY`）。DSH 与内核使用同一组值：

```text
baseURL    https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1
model      deepseek-v4.1-flash
apiKeyEnv  BAILIAN_API_KEY
maxTokens  8192
contextWindow 1000000
```

启动带 Super-agent 的 Web Harness：

```powershell
powershell -File scripts/run-web-super-agent.ps1 -Port 4780
# 或只起内核：
node src/cli.ts run seed.config.json
```

`App` 启动时会依次读取当前目录 `seed.env`、`.env`，也可用 `SEED_ENV_FILE` 指定其它路径。**已存在的系统环境变量优先，不会被覆盖。**

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
| `sources.github.repos` | 只处理这些仓库（`owner/name`），留空表示全部 |
| `sources.feishu` | 应用凭证的环境变量名 + 群 `chat_ids` + 可选 `sinceSeconds` |
| `slots` / `intervalMs` / `staleSeconds` | 并发、轮询间隔、Watchdog 停滞阈值 |

## 4. 体检与运行

```bash
node src/cli.ts doctor seed.config.json        # 只读体检：凭证/端点/gh/飞书/文件系统
node src/cli.ts run seed.config.json --once    # 跑一轮真实链路后退出
node src/cli.ts run seed.config.json           # 常驻（Ctrl+C 优雅退出）
node src/cli.ts panel seed.db                  # 只列"谁在等我"
node src/cli.ts panel seed.db --json           # 机器可读
node src/cli.ts say <chat_id> "文本"           # 飞书真实发送（验证用）
node src/cli.ts read <chat_id>                 # 飞书消息读取（过滤机器人/系统消息）
```

本地验证最小闭环：往 `inbox.jsonl` 追加一行

```json
{"id":"trg-1","source":"local","actor":"you","text":"在工单目录里写 hello.txt","threadIds":["local:1"],"channelIds":["local:1"]}
```

然后 `run --once`：模型受理 → 建工单 → 拉起 worker 进程 → worker 用文件工具写文件 → 回报 → Router 输出回复。

## 4.1 桌面版

`ash
node src/cli.ts desktop seed.config.json              # 引擎 + 独立应用窗口
node src/cli.ts desktop seed.config.json --no-browser # 只起服务
.\\scripts\\install-desktop.ps1                         # 桌面/开始菜单快捷方式
`

窗口是系统 Edge 的应用模式（独立 profile：%LOCALAPPDATA%\\seed-agent\\ui-profile），关窗即停引擎。

## 5. 数据与恢复

- 状态全在 `dbPath`（SQLite）：`events`（append-only）、`outbox`（stored work）、`cursors`（Source 位点）。
- 备份：直接复制 `seed.db`（WAL 模式建议先停进程）。
- 崩溃恢复：重启后 `run` 会调用 `recoverAfterRestart()`，把 running 的 assignment 收口并留下 `resume` 注记。
- 重放：`node -e "import('./src/store.ts').then(m=>{const s=new m.SqliteStore('seed.db');console.log(s.replayHash())})"` 可校验状态一致性。
- 安全网：非法事件在落库前被 reducer 拒绝；ID 工厂按历史事件预热，重启不会撞号。

## 6. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `missing env DEEPSEEK_API_KEY` | 凭证没进进程环境 | 检查 `seed.env` 或系统环境变量 |
| `model request failed: HTTP 401` | key 无效/过期 | 更新 key |
| `gh auth failed` | 未登录或 token 失效 | `gh auth login` |
| 工单停在 `working/queued` | worker 启动失败 | 看 worker stderr、检查 `workRoot` 权限 |
| 报告迟迟不回来 | 模型超时/worker 崩溃 | Watchdog 在 `staleSeconds` 后判停滞并重试 |
| 飞书 `code 99991663` | app_id/secret 或权限问题 | 检查应用凭证与 `im:message` 权限 |
| 飞书 `99991672` | 缺少 `im:chat` 权限 | doctor 会退化为按 chat_id 探读；需要列群时再申请 |

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

```bash
node scripts/live_watchdog.ts   # 真机：卡死 worker -> 模型判定 -> 重试（需 seed.env 模型 key）
node scripts/live_recovery.ts   # 真机：重启恢复（resume 输入 + 重新派工）
node scripts/live_github_comment.ts <owner/repo> <number> "文本"   # 真机：GitHub 评论回写并读回校验
```

## 9. 备份、恢复与 soak

在线备份（SQLite `VACUUM INTO`，不需要停服）：

```bash
node scripts/backup-super-agent.mjs seed.db backups/seed-$(date +%F).db
```

恢复：停服务 → 用备份替换 `dbPath` → 启动；不要直接复制正在写入的 `.db`（WAL 尚未合并）。

soak：

```bash
node --no-warnings scripts/soak-super-agent.mjs 5000
# 参考：events≈20012, delivered=5000, replayOk=true, ≈1600 events/s

# 长跑：持续追加 + 重复投递 + 每 100 批重启 + 重放校验；可断点续跑
node --no-warnings scripts/soak-long-super-agent.mjs --minutes 4320 --db /var/lib/seed-agent/soak.db
```

## 9b. 指标与探活

- `GET /health`：进程存活。
- `GET /metrics`：Prometheus 文本（`seed_daemon_requests_total`、`seed_daemon_errors_total`、`seed_daemon_events_buffered`、`seed_daemon_uptime_seconds`）。设置 token 后需 `Authorization: Bearer ...`。
- 建议告警：5 分钟错误增量、事件缓冲接近上限、进程重启次数。

## 10. 生产安全边界

- **Worker 环境最小化**：worker 只拿 `PATH/TEMP/HOME` 等基础变量和模型 key；飞书/GitHub 凭据不会进入 worker。
- **daemon 鉴权**：监听非 loopback 时必须设置 `SA_DAEMON_TOKEN`，否则拒绝启动。
- **daemon TLS**：可直接配置 `tls: { cert, key }` 启动 HTTPS；也可只监听 `127.0.0.1` 由反向代理终止 TLS。
- **模型凭据**：只放宿主 `seed.env`/systemd `EnvironmentFile`，权限 600；错误信息里的 `sk-`/Bearer 会被脱敏。
- **shell 工具**：worker 在宿主执行命令，隔离到工单目录但不是容器；高风险租户需容器/受限用户。
- **部署资产**：`deploy/Dockerfile`、`deploy/seed-agent.service`、`deploy/README.md`。

## 11. Router 对话历史

Router 的对话历史默认落盘到数据库同目录：

```text
<dbPath>.router-chat.json
```

- 只保存人类与 Router 的最近对话（最多 200 条），不含工单/事件状态。
- 进程重启后自动加载，因此“刚才聊过的内容”不会因重启丢失。
- 该文件与业务库一起备份；删除它等价于清空 Router 对话记忆。
- 内核 `seed.config.json` 与 DSH host 都使用同一路径规则。

## 12. 上线检查单

- [ ] `node --test "tests/*.test.ts"` 全绿（240 例）
- [ ] `node scripts/soak-super-agent.mjs 5000` → `SOAK OK`
- [ ] `node scripts/soak-long-super-agent.mjs --minutes 60` → `LONG SOAK OK`
- [ ] 备份脚本跑通且回放哈希一致
- [ ] Feishu/GitHub 出站真机各一条
- [ ] daemon 非 loopback 强制 token，TLS 或反代就绪
- [ ] `/health`、`/metrics` 接入监控
- [ ] 日志中无 `sk-`、app secret、daemon token
- [ ] systemd/Docker 按 `deploy/` 加固运行