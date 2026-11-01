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

```b```bash
node scripts/live_watchdog.ts   # 真机：卡死 worker -> 模型判定 -> 重试（需 seed.env 模型 key）
node scripts/live_recovery.ts   # 真机：重启恢复（resume 输入 + 重新派工）
node scripts/live_github_comment.ts <owner/repo> <number> "文本"   # 真机：GitHub 评论回写并读回校验
```
