# L4 SQLite + FTS5 存储方案设计文档

> **版本**: v1.0
> **日期**: 2026-04-19
> **状态**: 设计阶段

## 一、架构概览

### 1.1 当前架构 → 目标架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        当前架构 (JSONL)                          │
├─────────────────────────────────────────────────────────────────┤
│  AgentLoop._maybe_summarize()                                   │
│       ↓                                                          │
│  save_session_history(messages, summary, session_id)            │
│       ↓                                                          │
│  ~/.seed/memory/raw/sessions/*.jsonl  ←  O(n) 全扫描搜索        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        目标架构 (SQLite + FTS5)                  │
├─────────────────────────────────────────────────────────────────┤
│  AgentLoop._maybe_summarize()                                   │
│       ↓                                                          │
│  save_session_history(messages, summary, session_id)            │
│       ↓                                                          │
│  ~/.seed/memory/raw/sessions.db                                 │
│       ↓                                                          │
│  FTS5 全文索引  ←  O(1) 索引查询                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 变更范围

| 模块 | 是否需要改动 | 改动内容 |
|------|-------------|----------|
| `memory_tools.py` | ✅ **需要改动** | 替换文件 I/O 为 SQLite |
| `agent_loop.py` | ❌ **无需改动** | 调用接口不变 |
| `scheduler.py` | ❌ **无需改动** | 不直接读 L4 |
| `autonomous.py` | ❌ **无需改动** | 不直接读 L4 |

### 1.3 当前数据现状

| 维度 | 当前状态 | 数据 |
|------|----------|------|
| **数据量** | 14 MB, 15 个会话文件 | 最大单文件 13.7 MB |
| **存储格式** | JSONL (追加写入) | 每行一个 JSON 对象 |
| **查询模式** | 文件遍历 + 字符匹配 | O(n) 全扫描 |
| **并发** | 单线程 asyncio | 无锁、无 mutex |
| **用户模式** | 单用户 CLI | 无多实例需求 |
| **清理机制** | auto-dream 每 12 小时 | ROI 评估清理 |

---

## 二、数据库 Schema 设计

### 2.1 主表：session_messages

```sql
CREATE TABLE session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,          -- ISO 8601 格式
    role TEXT NOT NULL,               -- user/assistant/tool/system
    content TEXT,
    tool_calls_json TEXT,             -- JSON 序列化的 tool_calls
    tool_call_id TEXT,                -- 工具调用 ID（仅 tool role）
    message_type TEXT NOT NULL,       -- message/summary/meta
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 索引（非 FTS）
CREATE INDEX idx_session_messages_session ON session_messages(session_id);
CREATE INDEX idx_session_messages_timestamp ON session_messages(timestamp);
CREATE INDEX idx_session_messages_role ON session_messages(role);
```

### 2.2 FTS5 虚拟表：session_messages_fts

```sql
CREATE VIRTUAL TABLE session_messages_fts USING fts5(
    content,
    session_id,
    role,
    tokenize='unicode61 remove_diacritics 2',  -- 支持中文 + ASCII
    prefix='2 3 4',                             -- 前缀索引加速部分匹配
    content='session_messages',                 -- 外部内容表
    content_rowid='id'
);
```

### 2.3 触发器（自动同步）

```sql
-- INSERT 触发器
CREATE TRIGGER session_messages_ai AFTER INSERT ON session_messages 
WHEN new.message_type = 'message' BEGIN
    INSERT INTO session_messages_fts(rowid, content, session_id, role) 
    VALUES (new.id, new.content, new.session_id, new.role);
END;

-- DELETE 触发器
CREATE TRIGGER session_messages_ad AFTER DELETE ON session_messages 
WHEN old.message_type = 'message' BEGIN
    INSERT INTO session_messages_fts(session_messages_fts, rowid, content, session_id, role) 
    VALUES('delete', old.id, old.content, old.session_id, old.role);
END;

-- UPDATE 触发器
CREATE TRIGGER session_messages_au AFTER UPDATE ON session_messages 
WHEN old.message_type = 'message' AND new.message_type = 'message' BEGIN
    INSERT INTO session_messages_fts(session_messages_fts, rowid, content, session_id, role) 
    VALUES('delete', old.id, old.content, old.session_id, old.role);
    INSERT INTO session_messages_fts(rowid, content, session_id, role) 
    VALUES (new.id, new.content, new.session_id, new.role);
END;
```

### 2.4 元数据表：sessions_meta

```sql
CREATE TABLE sessions_meta (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    last_updated TEXT,
    message_count INTEGER DEFAULT 0,
    summary TEXT
);

CREATE INDEX idx_sessions_meta_created ON sessions_meta(created_at);
```

---

## 三、接口设计

### 3.1 新增模块位置

文件：`src/tools/session_db.py`

### 3.2 SessionDB 类设计

```python
"""
L4 Session 数据库存储层 (SQLite + FTS5)
替代原有的 JSONL 文件存储
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 数据库路径
DB_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions.db"


class SessionDB:
    """Session 数据库管理类"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库 Schema"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        # 性能优化 PRAGMA
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-32000;")
        
        # 创建表（上述 Schema）
        self._create_schema()
    
    def _create_schema(self):
        """创建数据库 Schema"""
        # ... SQL 创建语句见上方 Schema 设计
        pass
```

### 3.3 核心接口（保持与原函数签名兼容）

#### save_session_history

```python
def save_session_history(
    self, 
    messages: List[Dict], 
    summary: str = None, 
    session_id: str = None
) -> str:
    """
    保存会话历史到 SQLite
    
    Args:
        messages: 消息列表 [{role, content, tool_calls, ...}]
        summary: 可选摘要
        session_id: 会话 ID（如未提供则生成）
    
    Returns:
        "Session saved: {session_id} ({msg_count} messages)"
    """
    pass
```

#### load_session_history

```python
def load_session_history(self, session_id: str) -> str:
    """
    从 SQLite 加载指定会话
    
    Args:
        session_id: 会话 ID（支持模糊匹配）
    
    Returns:
        格式化会话数据
    """
    pass
```

#### list_sessions

```python
def list_sessions(self, limit: int = 10) -> str:
    """
    列出最近会话
    
    Args:
        limit: 返回数量限制
    
    Returns:
        "Recent Sessions:\n- {id}: {count} msgs..."
    """
    pass
```

#### search_history

```python
def search_history(self, keyword: str, limit: int = 20) -> str:
    """
    使用 FTS5 全文搜索
    
    Args:
        keyword: 搜索关键词
        limit: 结果限制
    
    Returns:
        "Found {count} matches for '{keyword}':\n..."
    """
    pass
```

### 3.4 新增接口（FTS5 增强）

#### search_with_filters

```python
def search_with_filters(
    self,
    keyword: str,
    session_id: Optional[str] = None,
    role: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 20
) -> List[Dict]:
    """
    增强搜索：支持多条件组合
    
    Args:
        keyword: 关键词
        session_id: 限定会话
        role: 限定角色
        start_time: 开始时间
        end_time: 结束时间
        limit: 结果限制
    
    Returns:
        匹配消息列表
    """
    pass
```

#### 索引维护

```python
def get_session_stats(self, session_id: str) -> Dict:
    """获取会话统计信息"""
    pass

def optimize_index(self):
    """优化 FTS5 索引"""
    self.conn.execute(
        "INSERT INTO session_messages_fts(session_messages_fts) VALUES('optimize')"
    )
    self.conn.commit()

def rebuild_index(self):
    """重建 FTS5 索引"""
    self.conn.execute(
        "INSERT INTO session_messages_fts(session_messages_fts) VALUES('rebuild')"
    )
    self.conn.commit()
```

---

## 四、迁移方案

### 4.1 迁移流程

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: 准备                                                   │
│ - 创建 sessions.db                                              │
│ - 初始化 Schema                                                 │
│ - 设置 PRAGMA 优化                                              │
├─────────────────────────────────────────────────────────────────┤
│ Phase 2: 数据迁移                                               │
│ - 遍历 ~/.seed/memory/raw/sessions/*.jsonl                      │
│ - 解析每行 JSON → 写入 SQLite                                   │
│ - batch_size=5000 批量插入                                      │
│ - 记录迁移进度（支持断点续传）                                   │
├─────────────────────────────────────────────────────────────────┤
│ Phase 3: 校验                                                   │
│ - 行数对比: JSONL 总行数 == SQLite COUNT(*)                     │
│ - PRAGMA integrity_check                                        │
│ - 验证 FTS5 搜索可用                                            │
├─────────────────────────────────────────────────────────────────┤
│ Phase 4: 切换                                                   │
│ - 修改 memory_tools.py 引用 session_db                          │
│ - 保留 JSONL 文件压缩备份                                       │
│ - 运行应用验证                                                   │
├─────────────────────────────────────────────────────────────────┤
│ Phase 5: 清理                                                   │
│ - 确认运行稳定后删除 JSONL 备份                                 │
│ - 定期执行 optimize_index()                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 迁移脚本位置

文件：`scripts/migrate_jsonl_to_sqlite.py`

### 4.3 迁移脚本核心逻辑

```python
"""
迁移脚本：migrate_jsonl_to_sqlite.py
"""

import json
import sqlite3
import gzip
import shutil
from pathlib import Path

SOURCE_DIR = Path.home() / ".seed" / "memory" / "raw" / "sessions"
DB_PATH = Path.home() / ".seed" / "memory" / "raw" / "sessions.db"
BACKUP_DIR = Path.home() / ".seed" / "memory" / "raw" / "sessions_backup"


def migrate():
    """执行迁移"""
    
    # Phase 1: 创建数据库
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA synchronous=OFF")  # 导入时禁用同步
    conn.execute("PRAGMA journal_mode=MEMORY")
    
    create_schema(conn)
    
    # Phase 2: 迁移数据
    total_lines = 0
    batch_size = 5000
    
    jsonl_files = sorted(SOURCE_DIR.glob("session_*.jsonl"))
    
    for jsonl_file in jsonl_files:
        session_id = jsonl_file.stem
        
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                
                obj = json.loads(line)
                msg_type = obj.get('type', 'message')
                
                # 根据 type 写入不同表
                if msg_type == 'session_meta':
                    # 写入 sessions_meta
                    pass
                elif msg_type == 'message':
                    # 写入 session_messages
                    pass
                elif msg_type == 'summary':
                    # 更新 sessions_meta.summary
                    pass
                
                total_lines += 1
                
                if total_lines % batch_size == 0:
                    conn.commit()
    
    conn.commit()
    
    # Phase 3: 校验
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result[0] != 'ok':
        raise RuntimeError(f"Database integrity check failed: {result}")
    
    # 重建 FTS5 索引
    conn.execute("INSERT INTO session_messages_fts(session_messages_fts) VALUES('rebuild')")
    conn.commit()
    
    # Phase 4: 备份 JSONL
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    for jsonl_file in jsonl_files:
        backup_path = BACKUP_DIR / f"{jsonl_file.name}.gz"
        with open(jsonl_file, 'rb') as f_in:
            with gzip.open(backup_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    
    conn.close()
```

---

## 五、性能预期

### 5.1 搜索性能对比

| 操作 | JSONL (当前) | SQLite + FTS5 (目标) | 提升 |
|------|-------------|---------------------|------|
| `search_history("关键词")` | O(n) 全扫描 ~2-5s | O(1) 索引查询 ~0.01s | **200x+** |
| `list_sessions()` | O(n) 遍历 ~0.5s | O(log n) 索引 ~0.01s | **50x+** |
| `load_session_history()` | O(1) 单文件读取 | O(1) 索引查询 | 相当 |

### 5.2 存储空间对比

| 维度 | JSONL | SQLite | 说明 |
|------|-------|--------|------|
| 文件体积 | 14 MB | ~10-12 MB | SQLite 更紧凑 |
| 索引开销 | 无 | +2-3 MB | FTS5 索引 |
| 总体积 | 14 MB | ~12-15 MB | 相当 |

---

## 六、中文支持方案

### 6.1 问题分析

`unicode61` 分词器将中文视为单字符，无法词级检索。

### 6.2 推荐方案：Python 层预处理 + jieba

```python
import jieba

def tokenize_for_fts5(text: str) -> str:
    """
    中文分词预处理
    
    Args:
        text: 原始文本
    
    Returns:
        分词后的文本（空格分隔）
    """
    tokens = jieba.cut(text)
    return ' '.join(tokens)

# 写入时预处理
content_for_fts = tokenize_for_fts5(original_content)

# 搜索时预处理
query_for_fts = tokenize_for_fts5(user_query)
```

### 6.3 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| Python + jieba | 无需 C 扩展、易实现 | 需额外依赖 | **★★★★☆ 推荐** |
| ICU 分词器 | 词级分割准确 | 需编译 C 扩展 | ★★★☆☆ |
| trigram | 内置无需配置 | 无词边界、噪音多 | ★★☆☆☆ |

---

## 七、实施检查清单

### 7.1 Phase 1: 开发

- [ ] 创建 `src/tools/session_db.py`
- [ ] 实现 `SessionDB` 类
- [ ] 实现 4 个核心接口（签名兼容）
- [ ] 创建 `scripts/migrate_jsonl_to_sqlite.py`
- [ ] 单元测试

### 7.2 Phase 2: 测试

- [ ] 本地测试迁移脚本
- [ ] 验证数据完整性
- [ ] 验证 FTS5 搜索可用
- [ ] 性能测试（搜索延迟）

### 7.3 Phase 3: 部署

- [ ] 运行迁移脚本
- [ ] 备份 JSONL 文件
- [ ] 切换 `memory_tools.py` 引用
- [ ] 验证应用运行正常
- [ ] 清理 JSONL 备份

---

## 八、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 迁移过程中数据丢失 | 高 | 保留 JSONL 压缩备份，校验后再删 |
| FTS5 中文搜索不准 | 中 | 使用 jieba 预处理 |
| SQLite 锁冲突 | 低 | WAL 模式 + busy_timeout |
| 索引体积过大 | 低 | 定期 optimize + 清理旧数据 |

---

## 九、数据流图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户输入                                   │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AgentLoop.run() / stream_run()                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ self.history.append(user_message)                               │ │
│  │ self._conversation_rounds += 1                                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                  │                                   │
│                                  ▼                                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ LLM 调用循环 (max_iterations)                                    │ │
│  │   - 构建 messages (system + history)                            │ │
│  │   - 执行 tool_calls                                             │ │
│  │   - 工具结果加入 history                                         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                  │                                   │
│                                  ▼                                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ _maybe_summarize() 触发条件:                                     │ │
│  │   - token 超过 75% 阈值                                         │ │
│  │   - 或轮次超过 summary_interval (默认10)                         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                  │                                   │
│              ┌───────────────────┼───────────────────┐              │
│              ▼                   ▼                   ▼              │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  │
│  │ SessionDB.save_  │  │  LLM 总结历史      │  │ 用摘要替换旧历史  │  │
│  │ session_history  │  │  → summary        │  │ → 保留最近4轮     │  │
│  │ (写入 SQLite)    │  │                   │  │ + 摘要            │  │
│  └─────────┬─────────┘  └───────────────────┘  └───────────────────┘  │
│            │                                                        │
└────────────┼────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│               ~/.seed/memory/raw/sessions.db                        │
│               (SQLite + FTS5)                                        │
│   - session_messages 表（消息数据）                                  │
│   - sessions_meta 表（会话元数据）                                   │
│   - session_messages_fts（FTS5 索引）                               │
└─────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│               用户通过工具访问                                       │
│   - SessionDB.search_history() → FTS5 全文搜索                      │
│   - SessionDB.load_session_history() → 加载单个会话                 │
│   - SessionDB.list_sessions() → 列出最近会话                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 十、接口契约定义

### 10.1 核心存储位置

```python
# session_db.py
DB_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions.db"
```

### 10.2 函数签名与契约

| 函数 | 输入 | 输出 | 用途 |
|------|------|------|------|
| `save_session_history` | messages[], summary, session_id | `"Session saved: {id} ({count} messages)"` | 写入 |
| `load_session_history` | session_id | 格式化文本 | 加载单个会话 |
| `list_sessions` | limit=10 | `"Recent Sessions:\n- {id}: {count} msgs..."` | 列表 |
| `search_history` | keyword, limit=20 | `"Found {count} matches for '{keyword}':\n..."` | 搜索 |

---

## 十一、总结

### 核心变更

仅 `memory_tools.py` → `session_db.py`，其他模块无需改动。

### 性能提升

搜索延迟从 2-5s 降至 0.01s（**200x+**）。

### 部署复杂度

零额外服务（SQLite 嵌入式），单文件 `sessions.db`。

### 中文支持

jieba 预处理方案，无需 C 扩展。

---

## 附录：参考资料

- [SQLite FTS5 官方文档](https://www.sqlite.org/fts5.html)
- [Python sqlite3 模块](https://docs.python.org/3/library/sqlite3.html)
- [jieba 中文分词](https://github.com/fxsjy/jieba)
- [sqlite-utils 工具](https://sqlite-utils.datasette.io/)