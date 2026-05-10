# 工具脚本目录

系统维护、迁移和诊断的独立工具脚本。

---

## 脚本列表

| 脚本 | 描述 |
|------|------|
| `migrate_jsonl_to_sqlite.py` | JSONL Session 文件迁移到 SQLite+FTS5 |

---

## migrate_jsonl_to_sqlite.py

**用途**：迁移 JSONL Session 历史到 SQLite+FTS5

**执行**：
```bash
python scripts/migrate_jsonl_to_sqlite.py
```

**选项**：
- `--dry-run`：预览迁移
- `--backup-dir`：指定 JSONL 备份位置
- `--verbose`：详细日志

**流程**：
1. 连接 SQLite
2. 读取 JSONL 文件
3. jieba 分词 → FTS5 索引
4. 验证迁移完整性
5. 创建 JSONL 备份

---

## 相关文档

- L4 设计：[docs/L4_SQLite_FTS5_Design.md](../docs/L4_SQLite_FTS5_Design.md)
- Session 工具：[src/tools/AGENTS.md](../src/tools/AGENTS.md)