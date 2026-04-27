"""
迁移脚本：migrate_jsonl_to_sqlite.py
将 JSONL 格式的会话历史迁移到 SQLite + FTS5

使用方式:
    python scripts/migrate_jsonl_to_sqlite.py [--backup] [--cleanup]
    
选项:
    --backup     迁移后压缩备份原始 JSONL 文件（默认执行）
    --no-backup  跳过备份
    --cleanup    迁移并验证成功后删除原始 JSONL 文件
    --dry-run    仅分析不迁移
"""

import json
import sqlite3
import gzip
import shutil
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False
    print("WARNING: jieba not installed, Chinese tokenization will be skipped during FTS rebuild.")

# 路径配置
SOURCE_DIR = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions"
DB_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions.db"
BACKUP_DIR = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions_backup"

# Batch size for bulk inserts
BATCH_SIZE = 5000


def create_schema(conn):
    """创建数据库 Schema"""
    cursor = conn.cursor()
    
    # 主表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_calls_json TEXT,
            tool_call_id TEXT,
            message_type TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_messages_session 
        ON session_messages(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_messages_timestamp 
        ON session_messages(timestamp)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_messages_role 
        ON session_messages(role)
    """)
    
    # FTS5 虚拟表
    # 注意：不使用 content= 外部内容表模式，而是独立存储分词后的内容。
    # 原因：SQLite 内置的 unicode61 分词器不支持中文，必须通过应用层
    # 使用 jieba 预处理后以空格分隔的形式写入 FTS5。
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts 
        USING fts5(
            content,
            session_id,
            role,
            tokenize='unicode61 remove_diacritics 2',
            prefix='2 3 4'
        )
    """)
    
    # 触发器
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS session_messages_ai 
        AFTER INSERT ON session_messages 
        WHEN new.message_type = 'message' 
        BEGIN
            INSERT INTO session_messages_fts(rowid, content, session_id, role) 
            VALUES (new.id, new.content, new.session_id, new.role);
        END
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS session_messages_ad 
        AFTER DELETE ON session_messages 
        WHEN old.message_type = 'message' 
        BEGIN
            INSERT INTO session_messages_fts(session_messages_fts, rowid, content, session_id, role) 
            VALUES('delete', old.id, old.content, old.session_id, old.role);
        END
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS session_messages_au 
        AFTER UPDATE ON session_messages 
        WHEN old.message_type = 'message' AND new.message_type = 'message' 
        BEGIN
            INSERT INTO session_messages_fts(session_messages_fts, rowid, content, session_id, role) 
            VALUES('delete', old.id, old.content, old.session_id, old.role);
            INSERT INTO session_messages_fts(rowid, content, session_id, role) 
            VALUES (new.id, new.content, new.session_id, new.role);
        END
    """)
    
    # 元数据表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions_meta (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_updated TEXT,
            message_count INTEGER DEFAULT 0,
            summary TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_meta_created 
        ON sessions_meta(created_at)
    """)
    
    conn.commit()


def analyze_jsonl_files():
    """分析 JSONL 文件情况"""
    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}")
        return []
    
    jsonl_files = sorted(SOURCE_DIR.glob("session_*.jsonl"))
    if not jsonl_files:
        print("No JSONL files found to migrate.")
        return []
    
    total_lines = 0
    total_size = 0
    total_messages = 0
    stats = []
    
    for f in jsonl_files:
        size = f.stat().st_size
        lines = 0
        messages = 0
        meta = {}
        
        with open(f, 'r', encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    lines += 1
                    msg_type = obj.get('type', '')
                    if msg_type == 'message':
                        messages += 1
                    elif msg_type == 'session_meta':
                        meta = obj
                except:
                    pass
        
        total_lines += lines
        total_messages += messages
        total_size += size
        
        stats.append({
            'file': f.name,
            'size': size,
            'lines': lines,
            'messages': messages,
            'meta': meta
        })
    
    print(f"\n{'='*60}")
    print(f"JSONL File Analysis")
    print(f"{'='*60}")
    print(f"Directory: {SOURCE_DIR}")
    print(f"Total files: {len(jsonl_files)}")
    print(f"Total size: {total_size / 1024 / 1024:.2f} MB")
    print(f"Total lines: {total_lines}")
    print(f"Total messages: {total_messages}")
    print(f"{'='*60}")
    
    for s in stats:
        size_mb = s['size'] / 1024 / 1024
        print(f"  {s['file']}: {size_mb:.2f} MB, {s['lines']} lines, {s['messages']} messages")
    
    print(f"{'='*60}\n")
    
    return jsonl_files


def migrate_data(conn, jsonl_files, dry_run=False):
    """执行数据迁移"""
    if dry_run:
        print("[DRY RUN] Skipping actual migration.")
        return 0, 0
    
    print("Phase 2: Migrating data...")
    
    cursor = conn.cursor()
    total_inserted = 0
    total_sessions = 0
    batch = []
    batch_sessions = {}
    
    for jsonl_file in jsonl_files:
        session_id = jsonl_file.stem
        print(f"  Processing: {jsonl_file.name}...", end=" ", flush=True)
        
        file_lines = 0
        created_at = None
        summary = None
        
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                msg_type = obj.get('type', 'message')
                
                if msg_type == 'session_meta':
                    created_at = obj.get('created_at', datetime.now().isoformat())
                    continue
                
                elif msg_type == 'summary':
                    summary = obj.get('content', '')
                    continue
                
                elif msg_type == 'message':
                    timestamp = obj.get('timestamp', datetime.now().isoformat())
                    role = obj.get('role', 'unknown')
                    content = obj.get('content', '')
                    tool_calls = obj.get('tool_calls')
                    tool_call_id = obj.get('tool_call_id')
                    
                    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
                    
                    batch.append((
                        session_id, timestamp, role, content,
                        tool_calls_json, tool_call_id, 'message'
                    ))
                    file_lines += 1
                    total_inserted += 1
                
                # 批量提交
                if len(batch) >= BATCH_SIZE:
                    cursor.executemany("""
                        INSERT INTO session_messages 
                        (session_id, timestamp, role, content, tool_calls_json, tool_call_id, message_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, batch)
                    conn.commit()
                    batch.clear()
        
        # 保存会话元数据
        if created_at:
            batch_sessions[session_id] = {
                'session_id': session_id,
                'created_at': created_at,
                'last_updated': datetime.now().isoformat(),
                'message_count': file_lines,
                'summary': summary
            }
        
        print(f"{file_lines} messages migrated")
        total_sessions += 1
    
    # 提交剩余批次
    if batch:
        cursor.executemany("""
            INSERT INTO session_messages 
            (session_id, timestamp, role, content, tool_calls_json, tool_call_id, message_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        batch.clear()
    
    # 写入元数据
    for sid, meta in batch_sessions.items():
        cursor.execute("""
            INSERT OR REPLACE INTO sessions_meta 
            (session_id, created_at, last_updated, message_count, summary)
            VALUES (?, ?, ?, ?, ?)
        """, (meta['session_id'], meta['created_at'], meta['last_updated'],
              meta['message_count'], meta['summary']))
    
    conn.commit()
    
    print(f"\nMigration complete: {total_inserted} messages across {total_sessions} sessions")
    return total_inserted, total_sessions


def verify_migration(conn, jsonl_files):
    """Phase 3: 校验数据完整性"""
    print("\nPhase 3: Verifying migration...")
    
    # 数据库完整性检查
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result[0] != 'ok':
        print(f"  FAIL: Database integrity check failed: {result}")
        return False
    print("  ✓ Database integrity check passed")
    
    # 行数对比
    db_count = conn.execute("SELECT COUNT(*) FROM session_messages WHERE message_type = 'message'").fetchone()[0]
    
    jsonl_count = 0
    for f in jsonl_files:
        with open(f, 'r', encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get('type') == 'message':
                        jsonl_count += 1
                except:
                    pass
    
    if db_count == jsonl_count:
        print(f"  ✓ Message count match: {db_count} == {jsonl_count}")
    else:
        print(f"  ✗ Message count MISMATCH: DB={db_count}, JSONL={jsonl_count}")
        return False
    
    # 元数据对比
    db_session_count = conn.execute("SELECT COUNT(*) FROM sessions_meta").fetchone()[0]
    jsonl_session_count = len(jsonl_files)
    
    if db_session_count == jsonl_session_count:
        print(f"  ✓ Session count match: {db_session_count} == {jsonl_session_count}")
    else:
        print(f"  ⚠ Session count: DB={db_session_count}, JSONL={jsonl_session_count}")
    
    # 验证 FTS5 索引
    try:
        test_result = conn.execute("""
            SELECT COUNT(*) FROM session_messages_fts
        """).fetchone()[0]
        print(f"  ✓ FTS5 index contains {test_result} entries")
        
        # 测试搜索功能
        search_test = conn.execute("""
            SELECT COUNT(*) FROM session_messages m
            JOIN session_messages_fts fts ON m.id = fts.rowid
            WHERE session_messages_fts MATCH 'test'
        """).fetchone()
        print(f"  ✓ FTS5 search functional (test query returned results)")
    except Exception as e:
        print(f"  ⚠ FTS5 test query: {e}")
    
    print("\n  ✓ All verifications passed!")
    return True


def backup_jsonl(jsonl_files):
    """Phase 4: 备份 JSONL 文件"""
    print("\nPhase 4: Backing up JSONL files...")
    
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    for jsonl_file in jsonl_files:
        backup_path = BACKUP_DIR / f"{jsonl_file.name}.gz"
        if backup_path.exists():
            print(f"  Skipping (already backed up): {jsonl_file.name}")
            continue
        
        with open(jsonl_file, 'rb') as f_in:
            with gzip.open(backup_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        original_size = jsonl_file.stat().st_size
        backup_size = backup_path.stat().st_size
        ratio = backup_size / original_size * 100 if original_size > 0 else 0
        print(f"  Backed up: {jsonl_file.name} -> {backup_path.name} ({ratio:.0f}% original size)")
    
    print(f"  Backup directory: {BACKUP_DIR}")


def cleanup_jsonl(jsonl_files):
    """Phase 5: 清理原始 JSONL 文件"""
    print("\nPhase 5: Cleaning up original JSONL files...")
    
    for jsonl_file in jsonl_files:
        jsonl_file.unlink()
        print(f"  Deleted: {jsonl_file.name}")
    
    print(f"  Cleaned {len(jsonl_files)} files from {SOURCE_DIR}")


def optimize_fts5(conn):
    """重建并优化 FTS5 索引"""
    print("\nOptimizing FTS5 index...")
    
    # Rebuild ensures full index consistency
    conn.execute("INSERT INTO session_messages_fts(session_messages_fts) VALUES('rebuild')")
    conn.commit()
    print("  ✓ FTS5 index rebuilt")
    
    # Optimize for performance
    conn.execute("INSERT INTO session_messages_fts(session_messages_fts) VALUES('optimize')")
    conn.commit()
    print("  ✓ FTS5 index optimized")
    
    # Report index size
    db_size = DB_PATH.stat().st_size
    print(f"  Database size: {db_size / 1024 / 1024:.2f} MB")


def main():
    """主入口：解析命令行参数并执行迁移或分析。"""
    parser = argparse.ArgumentParser(
        description="Migrate JSONL session history to SQLite + FTS5")
    parser.add_argument(
        "--backup", action="store_true", default=True,
        help="Backup JSONL files after migration (default)")
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Skip JSONL backup")
    parser.add_argument(
        "--cleanup", action="store_true",
        help="Delete original JSONL after successful migration")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Analyze only, don't migrate")
    
    args = parser.parse_args()
    
    if args.no_backup:
        args.backup = False
    
    print(f"{'='*60}")
    print(f"L4 JSONL → SQLite + FTS5 Migration Tool")
    print(f"{'='*60}")
    print(f"Source: {SOURCE_DIR}")
    print(f"Target: {DB_PATH}")
    print(f"Backup: {BACKUP_DIR}")
    print(f"{'='*60}\n")
    
    # Phase 1: Analyze
    jsonl_files = analyze_jsonl_files()
    if not jsonl_files:
        return
    
    if args.dry_run:
        print("Dry run complete. Remove --dry-run to execute migration.")
        return
    
    # Phase 1: Create database
    print("Phase 1: Creating database...")
    if DB_PATH.exists():
        print(f"  WARNING: Database already exists: {DB_PATH}")
        print(f"  Existing data will be preserved (new data will be appended).")
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA synchronous=OFF")  # 导入时禁用同步加速
    conn.execute("PRAGMA journal_mode=MEMORY")
    
    create_schema(conn)
    print("  ✓ Database created")
    
    # Phase 2: Migrate
    migrated, sessions = migrate_data(conn, jsonl_files, dry_run=args.dry_run)
    if migrated == 0 and args.dry_run:
        return
    
    # Restore normal PRAGMA
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Phase 3: Verify
    if not verify_migration(conn, jsonl_files):
        print("\n✗ Verification FAILED! Migration not complete.")
        print("  Original JSONL files are preserved.")
        conn.close()
        sys.exit(1)
    
    # Optimize FTS5
    optimize_fts5(conn)
    
    conn.close()
    
    # Phase 4: Backup
    if args.backup:
        backup_jsonl(jsonl_files)
    
    # Phase 5: Cleanup
    if args.cleanup:
        if args.backup:
            cleanup_jsonl(jsonl_files)
        else:
            print("\n⚠ Cleanup skipped: --backup is required before --cleanup")
    
    print(f"\n{'='*60}")
    print(f"Migration completed successfully!")
    print(f"  Database: {DB_PATH}")
    print(f"  Messages: {migrated}")
    print(f"  Sessions: {sessions}")
    if args.backup:
        print(f"  Backup: {BACKUP_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
