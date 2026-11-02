# 生产部署

## 1. Linux systemd

```bash
useradd --system --home /var/lib/seed-agent --shell /usr/sbin/nologin seed
install -d -o seed -g seed /opt/seed-agent /etc/seed-agent /var/lib/seed-agent /var/log/seed-agent
# 把仓库放到 /opt/seed-agent；配置放 /etc/seed-agent/seed.config.json
# 密钥放 /etc/seed-agent/seed.env（chmod 600, chown seed）
cp deploy/seed-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now seed-agent
```

`seed.config.json` 里 `dbPath` / `workRoot` 指到 `/var/lib/seed-agent/...`。
service 已启用 `ProtectSystem=strict`、`NoNewPrivileges`、`PrivateTmp`，只允许写状态/日志目录。

## 2. 容器

```bash
docker build -f deploy/Dockerfile -t seed-agent .
docker run -d --name seed-agent \
  -v $PWD/seed.config.json:/config/seed.config.json:ro \
  -v $PWD/seed.env:/run/secrets/seed.env:ro \
  -v seed-data:/data -v seed-work:/work \
  seed-agent
```

镜像不含 `dsh/`（桌面 host 另打安装包）；内核模式零第三方依赖，直接 `node src/cli.ts`。

## 3. TLS 与鉴权

- daemon 支持直接 TLS：配置 `tls: { cert, key }`；也可只监听 `127.0.0.1`，由反向代理终止 TLS。
- 非 loopback 监听必须设置 `SA_DAEMON_TOKEN`，否则启动失败（已测试）。
- Nginx 终止 TLS 示例：

```nginx
location / {
  proxy_pass http://127.0.0.1:64735;
  proxy_set_header Authorization "Bearer $SA_DAEMON_TOKEN";
  proxy_read_timeout 3600s;
}
```

## 4. 指标与健康

- `GET /health`：存活探针。
- `GET /metrics`：Prometheus 文本（请求数、错误数、事件缓冲、uptime）；设置 token 后需要 `Authorization: Bearer ...`。
- 建议告警：`seed_daemon_errors_total` 5 分钟增量、`seed_daemon_events_buffered` 持续接近上限、进程重启次数。

## 5. 备份与恢复

```bash
# 每日 02:00 在线备份（无需停服）
0 2 * * * seed /usr/bin/node /opt/seed-agent/scripts/backup-super-agent.mjs \
  /var/lib/seed-agent/seed.db /var/backups/seed/seed-$(date +\%F).db
```

恢复：`systemctl stop seed-agent` → 用备份替换 `dbPath` → `systemctl start seed-agent`。
备份文件与数据库同等级保密；用 `scripts/soak-super-agent.mjs` 校验新版本后再切流量。

## 6. 发布前门槛

```bash
node --test "tests/*.test.ts"
node --no-warnings scripts/soak-super-agent.mjs 5000   # SOAK OK, >=1000 events/s
node scripts/demo-article.mjs
cd dsh && pnpm run build                                # 10/10 gates（host 交付时）
```