# Module Overview - Utility Scripts

This directory contains utility scripts for system maintenance, migration, and diagnostics. These scripts are standalone tools that support the Seed Agent system but are not part of the core agent execution.

---

## Available Scripts

| Script | Description |
|--------|-------------|
| `migrate_jsonl_to_sqlite.py` | Migration tool for converting JSONL session files to SQLite+FTS5 |

---

## migrate_jsonl_to_sqlite.py

**Purpose:** Migrates existing JSONL session history files to SQLite+FTS5 database format.

**Usage:**
```bash
python scripts/migrate_jsonl_to_sqlite.py
```

**Features:**
- Reads all JSONL files from `~/.seed/memory/raw/sessions/`
- Creates SQLite database with proper schema
- Tokenizes content with jieba for FTS5 indexing
- Preserves all session metadata and summaries
- Validates migration integrity
- Creates backup of original JSONL files

**Migration Process:**
1. Connect to SQLite database (`sessions.db`)
2. Read each JSONL session file
3. Parse metadata and message entries
4. Insert into `session_messages` table
5. Tokenize content and insert into `session_messages_fts`
6. Update `sessions_meta` with summaries
7. Verify row counts match
8. Create backup directory for JSONL files

**Options:**
- `--dry-run`: Preview migration without executing
- `--backup-dir`: Specify backup location for JSONL files
- `--verbose`: Detailed logging output

---

## Future Scripts

Planned utility scripts to add:

| Planned Script | Purpose |
|----------------|---------|
| `diagnose_seed_agent.py` | System health check and diagnostics |
| `seed_config_manager.py` | Configuration validation and setup |
| `memory_cleanup.py` | Memory consolidation and cleanup tool |
| `ralph_task_manager.py` | Ralph Loop task file management |