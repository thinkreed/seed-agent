# DSH fork 的自有改动

本目录存放相对上游 deepseek-harness (ref: ce7073d5) 的**自有改动**，入库管理。

- `dsh/` 目录是按 `scripts/sync-dsh.ps1` 拉取的上游源码（1.3 万+文件 / 135MB），不入库。
- 我们的集成代码在 `dsh/packages/plugin/seed-agent`，最终以补丁形式导出到此目录：
  `git -C dsh diff --binary > contrib/dsh/seed-agent.patch`（或新文件清单）。
- 计划见 `docs/dsh-fork.md`。
