"""
L4 Session 数据库存储层 (SQLite + FTS5)
替代原有的 JSONL 文件存储，支持中文全文搜索

使用 jieba 进行中文分词预处理，通过 FTS5 实现高效搜索。

Memory Graph 增强:
- gene_outcomes 表: 存储 Skill 执行结果
- FTS5 虚拟表: 信号模式全文搜索
- 选择算法支持: 成功率统计、禁用阈值、Laplace 平滑
"""

import sqlite3
import json
import os
import re
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# 数据库路径
DB_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions.db"

# Memory Graph 配置参数
MEMORY_GRAPH_CONFIG = {
    'half_life_days': 30,           # 置信度衰减半衰期
    'ban_threshold': 0.18,          # 禁用阈值
    'min_attempts_for_ban': 2,      # 禁用前最小尝试次数
    'memory_weight': 0.6,           # 记忆分数权重
    'trigger_weight': 0.4,          # 触发匹配权重
    'cold_start_penalty': 0.5,      # 冷启动惩罚因子
    'recent_boost_factor': 0.2,     # 近期成功加成因子
    'recent_days': 30,              # "近期"定义天数
    'max_entries_per_skill': 5000,  # 每个 skill 最大记录数
}


def tokenize_for_fts5(text: str) -> str:
    """
    中文分词预处理
    - 如果有 jieba，使用 jieba 分词
    - 否则 fallback 到 unicode61（单字符）
    """
    if _HAS_JIEBA and text:
        tokens = jieba.cut(text)
        return ' '.join(tokens)
    return text or ''


def _sanitize_fts_query(query: str) -> str:
    """
    清理 FTS5 查询字符串，避免语法错误
    FTS5 特殊字符: " & | ( ) - : *
    """
    if _HAS_JIEBA and query:
        tokens = jieba.cut(query)
        query = ' '.join(tokens)

    for ch in ['"', '(', ')', ':']:
        query = query.replace(ch, '')

    query = re.sub(r'\bAND\b|\bOR\b|\bNOT\b', '', query, flags=re.IGNORECASE)

    return query.strip()


class SessionDB:
    """Session 数据库管理类 (SQLite + FTS5 + Memory Graph)"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self):
        """初始化数据库连接和 Schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # 性能优化 PRAGMA
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-32000;")

        self._create_schema()

    def _create_schema(self):
        """创建数据库 Schema"""
        self._create_session_messages_schema()
        self._create_sessions_meta_schema()
        self._create_gene_outcomes_schema()
        self._create_gene_outcomes_triggers()
        self._create_gene_outcomes_indexes()
        self.conn.commit()

    def _create_session_messages_schema(self):
        """创建 session_messages 表和索引"""
        cursor = self.conn.cursor()
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
        for idx in ['session_id', 'timestamp', 'role']:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_session_messages_{idx} ON session_messages({idx})")
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts
            USING fts5(content, session_id, role,
                tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')
        """)

    def _create_sessions_meta_schema(self):
        """创建 sessions_meta 表和索引"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions_meta (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                last_updated TEXT,
                message_count INTEGER DEFAULT 0,
                summary TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_meta_created ON sessions_meta(created_at)")

    def _create_gene_outcomes_schema(self):
        """创建 gene_outcomes 表和 FTS5 虚拟表"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gene_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                signal_pattern TEXT NOT NULL,
                outcome_status TEXT NOT NULL,
                outcome_score REAL NOT NULL,
                session_id TEXT,
                timestamp TEXT NOT NULL,
                iteration_context TEXT,
                intent TEXT,
                blast_radius TEXT,
                CONSTRAINT unique_outcome UNIQUE (skill_name, signal_pattern, timestamp)
            )
        """)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS gene_outcomes_fts USING fts5(
                signal_pattern, skill_name, outcome_status,
                content='gene_outcomes', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2')
        """)

    def _create_gene_outcomes_triggers(self):
        """创建 gene_outcomes FTS5 同步触发器"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS gene_outcomes_ai AFTER INSERT ON gene_outcomes BEGIN
                INSERT INTO gene_outcomes_fts(rowid, signal_pattern, skill_name, outcome_status)
                VALUES (new.id, new.signal_pattern, new.skill_name, new.outcome_status);
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS gene_outcomes_ad AFTER DELETE ON gene_outcomes BEGIN
                INSERT INTO gene_outcomes_fts(gene_outcomes_fts, rowid, signal_pattern, skill_name, outcome_status)
                VALUES ('delete', old.id, old.signal_pattern, old.skill_name, old.outcome_status);
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS gene_outcomes_au AFTER UPDATE ON gene_outcomes BEGIN
                INSERT INTO gene_outcomes_fts(gene_outcomes_fts, rowid, signal_pattern, skill_name, outcome_status)
                VALUES ('delete', old.id, old.signal_pattern, old.skill_name, old.outcome_status);
                INSERT INTO gene_outcomes_fts(rowid, signal_pattern, skill_name, outcome_status)
                VALUES (new.id, new.signal_pattern, new.skill_name, new.outcome_status);
            END
        """)

    def _create_gene_outcomes_indexes(self):
        """创建 gene_outcomes 索引"""
        cursor = self.conn.cursor()
        for col in ['skill_name', 'timestamp', 'outcome_status', 'session_id']:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_gene_{col} ON gene_outcomes({col})")

        self.conn.commit()

    def _parse_tool_calls(self, tool_calls) -> Optional[str]:
        """序列化 tool_calls 为 JSON"""
        if tool_calls:
            return json.dumps(tool_calls, ensure_ascii=False)
        return None

    # ==================== Memory Graph 方法 ====================

    def record_skill_outcome(
        self,
        skill_name: str,
        outcome: str,
        score: float = 1.0,
        signals: List[str] = None,
        session_id: str = None,
        context: str = None,
        intent: str = None,
        blast_radius: Dict = None
    ) -> str:
        """
        记录 Skill 执行结果到 gene_outcomes 表

        Args:
            skill_name: Skill 名称
            outcome: 执行结果 ('success' | 'failed' | 'partial')
            score: 成功分数 (0.0 - 1.0)
            signals: 触发信号列表
            session_id: 会话 ID
            context: 执行上下文摘要
            intent: 执行意图 ('repair' | 'optimize' | 'innovate')
            blast_radius: 影响范围 {"files": N, "lines": N}

        Returns:
            状态消息，包含更新后的统计信息
        """
        if outcome not in ('success', 'failed', 'partial'):
            return f"Invalid outcome status: {outcome}"

        if not (0.0 <= score <= 1.0):
            return f"Invalid score: {score} (must be 0.0-1.0)"

        signal_pattern = ' '.join(signals) if signals else ''
        timestamp = datetime.now().isoformat()
        blast_radius_json = json.dumps(blast_radius) if blast_radius else None

        try:
            self.conn.execute("""
                INSERT INTO gene_outcomes
                    (skill_name, signal_pattern, outcome_status, outcome_score,
                     session_id, timestamp, iteration_context, intent, blast_radius)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (skill_name, signal_pattern, outcome, score, session_id,
                  timestamp, context, intent, blast_radius_json))
            self.conn.commit()

            # 返回更新后的统计
            stats = self.get_skill_stats(skill_name)
            msg = (f"Outcome recorded: {skill_name} -> {outcome} "
                   f"(score: {score}). Stats: {stats['total']} total, "
                   f"{stats['success_rate']:.1%} success")
            return msg
        except sqlite3.IntegrityError:
            return f"Duplicate outcome ignored: {skill_name} at {timestamp}"
        except Exception as e:
            return f"Error recording outcome: {str(e)}"

    def _get_skill_basic_stats(self, skill_name: str) -> Dict:
        """获取 Skill 基础统计信息"""
        row = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN outcome_status = 'failed' THEN 1 ELSE 0 END) as failures,
                MAX(CASE WHEN outcome_status = 'success' THEN timestamp ELSE NULL END) as last_success,
                MAX(CASE WHEN outcome_status = 'failed' THEN timestamp ELSE NULL END) as last_failure,
                AVG(outcome_score) as avg_score
            FROM gene_outcomes
            WHERE skill_name = ?
        """, (skill_name,)).fetchone()
        return dict(row) if row else {}

    def _get_skill_recent_stats(self, skill_name: str, recent_days: int = 30) -> Dict:
        """获取 Skill 近期统计信息 (最近 N 天)"""
        recent_row = self.conn.execute("""
            SELECT
                COUNT(*) as recent_total,
                SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as recent_successes
            FROM gene_outcomes
            WHERE skill_name = ? AND timestamp > datetime('now', ?)
        """, (skill_name, f'-{recent_days} days')).fetchone()
        return dict(recent_row) if recent_row else {}

    def _compute_ban_status(self, skill_name: str, total: int, selection_value: float) -> bool:
        """检查 Skill 是否应被禁用"""
        min_attempts = MEMORY_GRAPH_CONFIG['min_attempts_for_ban']
        ban_threshold = MEMORY_GRAPH_CONFIG['ban_threshold']
        return total >= min_attempts and selection_value < ban_threshold

    def get_skill_stats(self, skill_name: str) -> Dict:
        """
        获取 Skill 的聚合统计信息

        Returns:
            {
                'total': N,
                'successes': N,
                'failures': N,
                'success_rate': 0.XX,
                'last_success': 'ISO timestamp',
                'last_failure': 'ISO timestamp',
                'recent_success_rate': 0.XX,
                'is_banned': bool,
                'selection_value': 0.XX,
                'laplace_rate': 0.XX
            }
        """
        try:
            row = self._get_skill_basic_stats(skill_name)

            if not row or row.get('total', 0) == 0:
                return {
                    'total': 0, 'successes': 0, 'failures': 0,
                    'success_rate': 0.0, 'recent_success_rate': 0.0,
                    'last_success': None, 'last_failure': None,
                    'is_banned': False, 'selection_value': 0.0,
                    'laplace_rate': 0.5  # 冷启动默认值
                }

            total = row['total']
            successes = row['successes']
            failures = row['failures']
            success_rate = successes / total if total > 0 else 0.0

            # Laplace 平滑
            laplace_rate = (successes + 1) / (total + 2)

            # 近期成功率 (最近 30 天)
            recent_days = MEMORY_GRAPH_CONFIG['recent_days']
            recent_row = self._get_skill_recent_stats(skill_name, recent_days)

            recent_success_rate = 0.0
            if recent_row and recent_row.get('recent_total', 0) > 0:
                recent_success_rate = recent_row['recent_successes'] / recent_row['recent_total']

            # 计算选择分数 (带衰减)
            selection_value = self._compute_selection_value(skill_name, successes, total, recent_success_rate)

            # 禁用检查
            is_banned = self._compute_ban_status(skill_name, total, selection_value)

            return {
                'total': total,
                'successes': successes,
                'failures': failures,
                'success_rate': success_rate,
                'laplace_rate': laplace_rate,
                'recent_success_rate': recent_success_rate,
                'last_success': row['last_success'],
                'last_failure': row['last_failure'],
                'avg_score': row['avg_score'],
                'is_banned': is_banned,
                'selection_value': selection_value
            }
        except Exception as e:
            return {'error': str(e)}

    def _compute_selection_value(
        self,
        skill_name: str,
        successes: int,
        total: int,
        recent_success_rate: float
    ) -> float:
        """
        计算选择分数 (GEP-style)

        公式: value = laplace_rate * decay_weight + recent_boost
        """
        half_life = MEMORY_GRAPH_CONFIG['half_life_days']
        recent_boost_factor = MEMORY_GRAPH_CONFIG['recent_boost_factor']

        # Laplace 平滑概率
        p = (successes + 1) / (total + 2)

        # 计算最近一次执行距今的天数（用于衰减）
        try:
            last_row = self.conn.execute("""
                SELECT MAX(timestamp) as last_time
                FROM gene_outcomes
                WHERE skill_name = ?
            """, (skill_name,)).fetchone()

            if last_row and last_row['last_time']:
                last_time = datetime.fromisoformat(last_row['last_time'])
                age_days = (datetime.now() - last_time).days
                decay_weight = 0.5 ** (age_days / half_life)
            else:
                decay_weight = 1.0  # 新记录不衰减
        except:
            decay_weight = 1.0

        # 近期成功加成
        recent_boost = recent_success_rate * recent_boost_factor

        return p * decay_weight + recent_boost

    def list_banned_skills(self) -> List[Dict]:
        """
        列出被禁用的 Skill（低于 ban_threshold）

        Returns:
            [
                {
                    'skill_name': 'xxx',
                    'total_attempts': N,
                    'current_value': 0.XX,
                    'success_rate': 0.XX,
                    'ban_reason': 'Low success rate',
                    'suggested_action': 'Review strategy or retire'
                }
            ]
        """
        min_attempts = MEMORY_GRAPH_CONFIG['min_attempts_for_ban']
        ban_threshold = MEMORY_GRAPH_CONFIG['ban_threshold']

        try:
            rows = self.conn.execute("""
                SELECT
                    skill_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
                    MAX(timestamp) as last_time
                FROM gene_outcomes
                GROUP BY skill_name
                HAVING COUNT(*) >= ?
            """, (min_attempts,)).fetchall()

            banned = []
            for row in rows:
                stats = self.get_skill_stats(row['skill_name'])
                if stats['selection_value'] < ban_threshold:
                    banned.append({
                        'skill_name': row['skill_name'],
                        'total_attempts': row['total'],
                        'current_value': stats['selection_value'],
                        'success_rate': stats['success_rate'],
                        'laplace_rate': stats['laplace_rate'],
                        'last_time': row['last_time'],
                        'ban_reason': 'Low success rate',
                        'suggested_action': 'Review strategy or retire'
                    })

            return banned
        except Exception as e:
            return []

    def get_top_skills(self, limit: int = 10) -> List[Dict]:
        """
        获取成功率最高的 Skill

        Returns:
            按 selection_value 排序的 Skill 列表
        """
        try:
            rows = self.conn.execute("""
                SELECT DISTINCT skill_name FROM gene_outcomes
            """).fetchall()

            skill_values = []
            for row in rows:
                stats = self.get_skill_stats(row['skill_name'])
                if stats['total'] > 0:
                    skill_values.append({
                        'skill_name': row['skill_name'],
                        'selection_value': stats['selection_value'],
                        'success_rate': stats['success_rate'],
                        'total': stats['total']
                    })

            # 按选择分数排序
            skill_values.sort(key=lambda x: x['selection_value'], reverse=True)
            return skill_values[:limit]
        except Exception as e:
            return []

    def search_outcomes_by_signal(self, signal: str, limit: int = 20) -> List[Dict]:
        """
        根据信号模式搜索历史执行结果

        Args:
            signal: 搜索信号
            limit: 结果限制

        Returns:
            匹配的执行记录列表
        """
        try:
            fts_query = _sanitize_fts_query(signal)
            if not fts_query:
                return []

            rows = self.conn.execute("""
                SELECT
                    g.id, g.skill_name, g.signal_pattern, g.outcome_status, g.outcome_score, g.timestamp
                FROM gene_outcomes g
                JOIN gene_outcomes_fts fts ON g.id = fts.rowid
                WHERE gene_outcomes_fts MATCH ?
                ORDER BY g.timestamp DESC
                LIMIT ?
            """, (fts_query, limit)).fetchall()

            return [dict(row) for row in rows]
        except Exception as e:
            return []

    def cleanup_old_outcomes(self, max_entries_per_skill: int = None):
        """
        清理过旧的执行记录 (FIFO)

        Args:
            max_entries_per_skill: 每个 Skill 最大保留记录数
        """
        max_entries = max_entries_per_skill or MEMORY_GRAPH_CONFIG['max_entries_per_skill']

        try:
            # 找出超限的 Skill
            rows = self.conn.execute("""
                SELECT skill_name, COUNT(*) as count
                FROM gene_outcomes
                GROUP BY skill_name
                HAVING COUNT(*) > ?
            """, (max_entries,)).fetchall()

            for row in rows:
                skill_name = row['skill_name']
                excess = row['count'] - max_entries

                # 删除最旧的记录
                self.conn.execute("""
                    DELETE FROM gene_outcomes
                    WHERE skill_name = ? AND id IN (
                        SELECT id FROM gene_outcomes
                        WHERE skill_name = ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                """, (skill_name, skill_name, excess))

            self.conn.commit()
        except Exception as e:
            pass

    # ==================== 原有 Session 方法 ====================

    def _build_message_batches(
        self, messages: List[Dict], session_id: str, now: str
    ) -> Tuple[List[Tuple], List[Tuple]]:
        """构建消息批次 (session_messages + FTS)"""
        batch = []
        fts_batch = []
        for msg in messages:
            ts = msg.get('timestamp', now)
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            tool_calls = self._parse_tool_calls(msg.get('tool_calls'))
            tool_call_id = msg.get('tool_call_id')

            batch.append((session_id, ts, role, content, tool_calls, tool_call_id, 'message'))
            tokenized = tokenize_for_fts5(content) if content else ''
            fts_batch.append((session_id, tokenized, role))
        return batch, fts_batch

    def _insert_fts_index(self, cursor, fts_batch: List[Tuple], start_id: int):
        """插入 FTS 索引"""
        for i, (sid, tokenized, role) in enumerate(fts_batch):
            rowid = start_id + i
            cursor.execute(
                "INSERT INTO session_messages_fts(rowid, content, session_id, role) VALUES (?, ?, ?, ?)",
                (rowid, tokenized, sid, role)
            )

    def _upsert_session_meta(self, cursor, session_id: str, now: str, msg_count: int, summary: str, is_new: bool):
        """插入或更新会话元数据"""
        if is_new:
            cursor.execute(
                "INSERT INTO sessions_meta "
                "(session_id, created_at, last_updated, message_count, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, now, now, msg_count, summary)
            )
        else:
            cursor.execute(
                "UPDATE sessions_meta SET last_updated = ?, "
                "message_count = message_count + ?, "
                "summary = COALESCE(?, summary) WHERE session_id = ?",
                (now, msg_count, summary, session_id)
            )

    def save_session_history(
        self,
        messages: List[Dict],
        summary: str = None,
        session_id: str = None
    ) -> str:
        """保存会话历史到 SQLite"""
        try:
            if not session_id:
                session_id = self._generate_session_filename()

            now = datetime.now().isoformat()

            existing = self.conn.execute(
                "SELECT session_id FROM sessions_meta WHERE session_id = ?", (session_id,)
            ).fetchone()
            is_new = existing is None

            cursor = self.conn.cursor()
            batch, fts_batch = self._build_message_batches(messages, session_id, now)

            cursor.executemany(
                "INSERT INTO session_messages "
                "(session_id, timestamp, role, content, tool_calls_json, "
                " tool_call_id, message_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                batch
            )

            if batch:
                # executemany doesn't set lastrowid, so query for it
                start_id = cursor.execute("SELECT MAX(id) FROM session_messages").fetchone()[0] - len(batch) + 1
                self._insert_fts_index(cursor, fts_batch, start_id)

            msg_count = len(messages)
            self._upsert_session_meta(cursor, session_id, now, msg_count, summary, is_new)

            self.conn.commit()
            return f"Session saved: {session_id} ({msg_count} messages)"
        except Exception as e:
            self.conn.rollback()
            return f"Error saving session: {str(e)}"

    def load_session_history(self, session_id: str) -> str:
        """从 SQLite 加载指定会话"""
        try:
            row = self.conn.execute(
                "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id = ?",
                (session_id,)
            ).fetchone()

            if not row:
                row = self.conn.execute(
                    "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id LIKE ?",
                    (f"%{session_id}%",)
                ).fetchone()

            if not row:
                return f"Session not found: {session_id}"

            actual_id = row['session_id']
            created_at = row['created_at']
            summary = row['summary']
            msg_count = row['message_count']

            messages = self.conn.execute("""
                SELECT id, timestamp, role, content, tool_calls_json, tool_call_id
                FROM session_messages
                WHERE session_id = ? AND message_type = 'message'
                ORDER BY id ASC
            """, (actual_id,)).fetchall()

            output = f"Session: {actual_id}\n"
            output += f"Created: {created_at}\n"
            output += f"Messages: {msg_count}\n"
            if summary:
                output += f"Summary: {summary}\n"
            output += "---\n"

            for msg in messages:
                role = msg['role']
                content = msg['content'] or ''
                if msg['tool_calls_json']:
                    try:
                        tc_list = json.loads(msg['tool_calls_json'])
                        tc_names = [tc.get('function', {}).get('name', 'unknown') for tc in tc_list]
                        content = f"[Tool Calls: {', '.join(tc_names)}]"
                    except:
                        pass
                if msg['tool_call_id']:
                    content = (msg['content'] or '')[:200]

                if len(content) > 500:
                    content = content[:500] + "..."

                output += f"{role}: {content}\n"

            return output
        except Exception as e:
            return f"Error loading session: {str(e)}"

    def list_sessions(self, limit: int = 10) -> str:
        """列出最近会话"""
        try:
            sessions = self.conn.execute("""
                SELECT session_id, created_at, last_updated, message_count, summary
                FROM sessions_meta
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

            if not sessions:
                return "No sessions found."

            output = "Recent Sessions:\n"
            for s in sessions:
                output += f"- {s['session_id']}: {s['message_count']} msgs, {s['created_at']}\n"
                if s['summary']:
                    summary_text = s['summary'][:100] if s['summary'] else ''
                    if summary_text:
                        output += f"  Summary: {summary_text}...\n"

            return output
        except Exception as e:
            return f"Error listing sessions: {str(e)}"

    def search_history(self, keyword: str, limit: int = 20) -> str:
        """使用 FTS5 全文搜索"""
        try:
            if not keyword.strip():
                return "Please provide a search keyword."

            fts_query = _sanitize_fts_query(keyword)
            if not fts_query:
                return f"No matches found for: {keyword}"

            query_expr = fts_query

            has_cjk = any('\u4e00' <= c <= '\u9fff' for c in fts_query)

            if has_cjk:
                tokens = fts_query.split()
                if len(tokens) > 1:
                    query_expr = ' OR '.join(tokens)

            results = self.conn.execute("""
                SELECT
                    m.session_id, m.timestamp, m.role, m.content, m.tool_call_id,
                    m.id as msg_id
                FROM session_messages m
                JOIN session_messages_fts fts ON m.id = fts.rowid
                WHERE session_messages_fts MATCH ?
                AND m.message_type = 'message'
                ORDER BY fts.rank
                LIMIT ?
            """, (query_expr, limit)).fetchall()

            if not results:
                return self._fallback_search(keyword, limit)

            output = f"Found {len(results)} matches for '{keyword}':\n"
            for r in results:
                content = r['content'] or ''
                matched_preview = self._highlight_match(content, keyword)
                context = self._get_context(r['session_id'], r['msg_id'], 1)

                output += f"\n[{r['session_id']}] {r['timestamp']}\n"
                output += f"{r['role']}: {matched_preview}\n"
                output += f"Context: {context}\n"

            return output
        except sqlite3.OperationalError as e:
            return self._fallback_search(keyword, limit)
        except Exception as e:
            return f"Error searching history: {str(e)}"

    def _fallback_search(self, keyword: str, limit: int = 20) -> str:
        """简单的字符串匹配搜索"""
        try:
            results = self.conn.execute("""
                SELECT session_id, timestamp, role, content, id as msg_id
                FROM session_messages
                WHERE content LIKE ? AND message_type = 'message'
                LIMIT ?
            """, (f"%{keyword}%", limit)).fetchall()

            if not results:
                return f"No matches found for: {keyword}"

            output = f"Found {len(results)} matches for '{keyword}':\n"
            for r in results:
                content = r['content'] or ''
                matched_preview = self._highlight_match(content, keyword)
                context = self._get_context(r['session_id'], r['msg_id'], 1)
                output += f"\n[{r['session_id']}] {r['timestamp']}\n"
                output += f"{r['role']}: {matched_preview}\n"
                output += f"Context: {context}\n"

            return output
        except Exception as e:
            return f"Error in fallback search: {str(e)}"

    def _highlight_match(self, content: str, keyword: str, max_len: int = 300) -> str:
        """高亮匹配部分"""
        if not content:
            return ""

        idx = content.lower().find(keyword.lower())
        if idx == -1:
            return content[:max_len] + ("..." if len(content) > max_len else "")

        start = max(0, idx - 50)
        end = min(len(content), idx + len(keyword) + 250)
        preview = content[start:end]
        if start > 0:
            preview = "..." + preview
        if end < len(content):
            preview = preview + "..."

        return preview

    def _get_context(self, session_id: str, msg_id: int, context_size: int = 1) -> str:
        """获取消息的上下文"""
        try:
            context_msgs = self.conn.execute("""
                SELECT role, content
                FROM session_messages
                WHERE session_id = ? AND message_type = 'message'
                AND id BETWEEN ? AND ?
                ORDER BY id ASC
            """, (session_id, msg_id - context_size, msg_id + context_size)).fetchall()

            return [f"{m['role']}: {(m['content'] or '')[:100]}" for m in context_msgs]
        except:
            return []

    def _apply_filters(
        self,
        base_sql: str,
        params: list,
        session_id: Optional[str],
        role: Optional[str],
        start_time: Optional[str],
        end_time: Optional[str],
        order_by: str,
        limit: int
    ) -> Tuple[str, list]:
        """添加通用过滤条件到 SQL 查询"""
        if session_id:
            base_sql += " AND m.session_id = ?"
            params.append(session_id)
        if role:
            base_sql += " AND m.role = ?"
            params.append(role)
        if start_time:
            base_sql += " AND m.timestamp >= ?"
            params.append(start_time)
        if end_time:
            base_sql += " AND m.timestamp <= ?"
            params.append(end_time)

        base_sql += f" ORDER BY {order_by} LIMIT ?"
        params.append(limit)
        return base_sql, params

    def search_with_filters(
        self,
        keyword: str,
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """增强搜索：支持多条件组合"""
        try:
            # 基础查询模板
            SELECT_CLAUSE = """
                SELECT m.id, m.session_id, m.timestamp, m.role, m.content, m.tool_calls_json, m.tool_call_id
                FROM session_messages m
            """
            WHERE_CLAUSE = "WHERE m.message_type = 'message'"

            if keyword.strip():
                fts_query = _sanitize_fts_query(keyword)
                if not fts_query:
                    return []

                base_sql = f"""{SELECT_CLAUSE}
                    JOIN session_messages_fts fts ON m.id = fts.rowid
                    {WHERE_CLAUSE}
                    AND session_messages_fts MATCH ?
                """
                params = [fts_query]
                order_by = "fts.rank"
            else:
                base_sql = f"{SELECT_CLAUSE} {WHERE_CLAUSE}"
                params = []
                order_by = "m.timestamp DESC"

            base_sql, params = self._apply_filters(
                base_sql, params, session_id, role, start_time, end_time, order_by, limit
            )

            rows = self.conn.execute(base_sql, params).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def get_session_stats(self, session_id: str) -> Dict:
        """获取会话统计信息"""
        try:
            meta = self.conn.execute(
                "SELECT * FROM sessions_meta WHERE session_id = ?",
                (session_id,)
            ).fetchone()

            if not meta:
                return {"error": "Session not found"}

            fts_size = self.conn.execute("""
                SELECT COUNT(*) as fts_count
                FROM session_messages_fts
                WHERE session_id = ?
            """, (session_id,)).fetchone()

            return {
                "session_id": meta["session_id"],
                "created_at": meta["created_at"],
                "last_updated": meta["last_updated"],
                "message_count": meta["message_count"],
                "fts_indexed_count": fts_size["fts_count"],
                "has_summary": bool(meta["summary"])
            }
        except Exception as e:
            return {"error": str(e)}

    def optimize_index(self):
        """优化 FTS5 索引"""
        try:
            self.conn.execute(
                "INSERT INTO session_messages_fts(session_messages_fts) VALUES('optimize')"
            )
            self.conn.commit()
            return "FTS5 index optimized."
        except Exception as e:
            return f"Error optimizing index: {str(e)}"

    def rebuild_index(self):
        """重建 FTS5 索引"""
        try:
            self.conn.execute(
                "INSERT INTO session_messages_fts(session_messages_fts) VALUES('rebuild')"
            )
            self.conn.commit()
            return "FTS5 index rebuilt."
        except Exception as e:
            return f"Error rebuilding index: {str(e)}"

    def _generate_session_filename(self) -> str:
        """生成会话文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}.jsonl"

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __del__(self):
        try:
            self.close()
        except:
            pass


# ==================== 模块级便捷函数 ====================

_db_instance = None

def _get_db() -> SessionDB:
    """获取全局 SessionDB 实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = SessionDB()
    return _db_instance


def save_session_history(messages: list, summary: str = None, session_id: str = None) -> str:
    """Save conversation history to SQLite"""
    return _get_db().save_session_history(messages, summary, session_id)


def load_session_history(session_id: str) -> str:
    """Load conversation history from SQLite"""
    return _get_db().load_session_history(session_id)


def list_sessions(limit: int = 10) -> str:
    """List recent sessions from SQLite"""
    return _get_db().list_sessions(limit)


def search_history(keyword: str, limit: int = 20) -> str:
    """Search conversation history using FTS5"""
    return _get_db().search_history(keyword, limit)


# ==================== Memory Graph 便捷函数 ====================

def record_skill_outcome(
    skill_name: str,
    outcome: str,
    score: float = 1.0,
    signals: List[str] = None,
    session_id: str = None,
    context: str = None
) -> str:
    """记录 Skill 执行结果"""
    return _get_db().record_skill_outcome(skill_name, outcome, score, signals, session_id, context)


def get_skill_stats(skill_name: str) -> Dict:
    """获取 Skill 统计信息"""
    return _get_db().get_skill_stats(skill_name)


def list_banned_skills() -> List[Dict]:
    """列出被禁用的 Skill"""
    return _get_db().list_banned_skills()


def get_top_skills(limit: int = 10) -> List[Dict]:
    """获取成功率最高的 Skill"""
    return _get_db().get_top_skills(limit)


def search_outcomes_by_signal(signal: str, limit: int = 20) -> List[Dict]:
    """根据信号搜索执行结果"""
    return _get_db().search_outcomes_by_signal(signal, limit)