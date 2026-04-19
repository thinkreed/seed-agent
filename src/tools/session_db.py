"""
L4 Session 数据库存储层 (SQLite + FTS5)
替代原有的 JSONL 文件存储，支持中文全文搜索

使用 jieba 进行中文分词预处理，通过 FTS5 实现高效搜索。
"""

import sqlite3
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# 数据库路径
DB_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "raw" / "sessions.db"


def tokenize_for_fts5(text: str) -> str:
    """
    中文分词预处理
    - 如果有 jieba，使用 jieba 分词
    - 否则 fallback 到 unicode61（单字符）
    """
    if _HAS_JIEBA and text:
        # 只对中文字符部分使用 jieba
        # 保留 ASCII 单词边界，中文分词
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
    
    # 转义 FTS5 特殊字符
    for ch in ['"', '(', ')', ':']:
        query = query.replace(ch, '')
    
    # 处理 AND/OR/NOT 操作符
    query = re.sub(r'\bAND\b|\bOR\b|\bNOT\b', '', query, flags=re.IGNORECASE)
    
    return query.strip()


class SessionDB:
    """Session 数据库管理类 (SQLite + FTS5)"""
    
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
        cursor = self.conn.cursor()
        
        # 主表：session_messages
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
        
        # 索引（非 FTS）
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
        
        # 元数据表：sessions_meta
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
        
        self.conn.commit()
    
    def _parse_tool_calls(self, tool_calls) -> Optional[str]:
        """序列化 tool_calls 为 JSON"""
        if tool_calls:
            return json.dumps(tool_calls, ensure_ascii=False)
        return None
    
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
        try:
            if not session_id:
                session_id = self._generate_session_filename()
            
            now = datetime.now().isoformat()
            
            # 检查是否是新会话
            existing = self.conn.execute(
                "SELECT session_id FROM sessions_meta WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            
            is_new = existing is None
            
            cursor = self.conn.cursor()
            
            # 写入消息
            batch = []
            fts_batch = []
            for msg in messages:
                ts = msg.get('timestamp', now)
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                tool_calls = self._parse_tool_calls(msg.get('tool_calls'))
                tool_call_id = msg.get('tool_call_id')
                
                batch.append((
                    session_id, ts, role, content,
                    tool_calls, tool_call_id, 'message'
                ))
                
                # FTS5: 使用 jieba 分词后的内容（空格分隔）
                tokenized = tokenize_for_fts5(content) if content else ''
                fts_batch.append((session_id, tokenized, role))
            
            cursor.executemany("""
                INSERT INTO session_messages 
                (session_id, timestamp, role, content, tool_calls_json, tool_call_id, message_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, batch)
            
            # 插入 FTS5 索引（使用分词后的内容，rowid 与主表对应）
            # 获取刚插入的行的 rowid 范围
            if batch:
                # 使用 cursor.lastrowid 获取最后插入的 ID
                last_id = cursor.lastrowid
                start_id = last_id - len(batch) + 1
                
                for i, (sid, tokenized, role) in enumerate(fts_batch):
                    rowid = start_id + i
                    cursor.execute("""
                        INSERT INTO session_messages_fts(rowid, content, session_id, role)
                        VALUES (?, ?, ?, ?)
                    """, (rowid, tokenized, sid, role))
            
            # 更新或创建元数据
            msg_count = len(messages)
            if is_new:
                cursor.execute("""
                    INSERT INTO sessions_meta (session_id, created_at, last_updated, message_count, summary)
                    VALUES (?, ?, ?, ?, ?)
                """, (session_id, now, now, msg_count, summary))
            else:
                cursor.execute("""
                    UPDATE sessions_meta 
                    SET last_updated = ?, message_count = message_count + ?, summary = COALESCE(?, summary)
                    WHERE session_id = ?
                """, (now, msg_count, summary, session_id))
            
            self.conn.commit()
            
            return f"Session saved: {session_id} ({msg_count} messages)"
        except Exception as e:
            self.conn.rollback()
            return f"Error saving session: {str(e)}"
    
    def load_session_history(self, session_id: str) -> str:
        """
        从 SQLite 加载指定会话
        
        Args:
            session_id: 会话 ID（支持模糊匹配）
        
        Returns:
            格式化会话数据
        """
        try:
            # 先精确匹配
            row = self.conn.execute(
                "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            
            if not row:
                # 模糊匹配
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
            
            # 查询消息
            messages = self.conn.execute("""
                SELECT id, timestamp, role, content, tool_calls_json, tool_call_id
                FROM session_messages
                WHERE session_id = ? AND message_type = 'message'
                ORDER BY id ASC
            """, (actual_id,)).fetchall()
            
            # 格式化输出
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
        """
        列出最近会话
        
        Args:
            limit: 返回数量限制
        
        Returns:
            "Recent Sessions:\n- {id}: {count} msgs..."
        """
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
        """
        使用 FTS5 全文搜索（支持中文）
        
        Args:
            keyword: 搜索关键词
            limit: 结果限制
        
        Returns:
            "Found {count} matches for '{keyword}':\n..."
        """
        try:
            if not keyword.strip():
                return "Please provide a search keyword."
            
            # FTS5 查询预处理
            fts_query = _sanitize_fts_query(keyword)
            if not fts_query:
                return f"No matches found for: {keyword}"
            
            # 使用 FTS5 搜索（独立表，内容为 jieba 分词结果）
            # 对于中文，使用 OR 逻辑组合分词后的 tokens 来提高召回率
            query_expr = fts_query
            
            # 检测是否包含中文字符
            has_cjk = any('\u4e00' <= c <= '\u9fff' for c in fts_query)
            
            if has_cjk:
                # 中文使用 OR 逻辑：任一 token 匹配即返回
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
                # Fallback: 简单字符串匹配
                return self._fallback_search(keyword, limit)
            
            output = f"Found {len(results)} matches for '{keyword}':\n"
            for r in results:
                content = r['content'] or ''
                matched_preview = self._highlight_match(content, keyword)
                
                # 获取上下文
                context = self._get_context(r['session_id'], r['msg_id'], 1)
                
                output += f"\n[{r['session_id']}] {r['timestamp']}\n"
                output += f"{r['role']}: {matched_preview}\n"
                output += f"Context: {context}\n"
            
            return output
        except sqlite3.OperationalError as e:
            # FTS5 查询语法错误，fallback 到简单搜索
            return self._fallback_search(keyword, limit)
        except Exception as e:
            return f"Error searching history: {str(e)}"
    
    def _fallback_search(self, keyword: str, limit: int = 20) -> str:
        """简单的字符串匹配搜索（当 FTS5 不可用时的后备方案）"""
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
        """高亮匹配部分（简化为截断预览）"""
        if not content:
            return ""
        
        idx = content.lower().find(keyword.lower())
        if idx == -1:
            return content[:max_len] + ("..." if len(content) > max_len else "")
        
        # 显示匹配位置周围的文本
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
    
    # ==================== 增强搜索接口 ====================
    
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
        try:
            if keyword.strip():
                fts_query = _sanitize_fts_query(keyword)
                if not fts_query:
                    return []
                
                # 构建 FTS5 查询
                base_sql = """
                    SELECT m.id, m.session_id, m.timestamp, m.role, m.content, m.tool_calls_json, m.tool_call_id
                    FROM session_messages m
                    JOIN session_messages_fts fts ON m.id = fts.rowid
                    WHERE session_messages_fts MATCH ?
                    AND m.message_type = 'message'
                """
                params = [fts_query]
                
                # 添加过滤条件
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
                
                base_sql += " ORDER BY fts.rank LIMIT ?"
                params.append(limit)
                
                rows = self.conn.execute(base_sql, params).fetchall()
            else:
                # 无关键词，仅过滤
                base_sql = """
                    SELECT m.id, m.session_id, m.timestamp, m.role, m.content, m.tool_calls_json, m.tool_call_id
                    FROM session_messages m
                    WHERE m.message_type = 'message'
                """
                params = []
                
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
                
                base_sql += " ORDER BY m.timestamp DESC LIMIT ?"
                params.append(limit)
                
                rows = self.conn.execute(base_sql, params).fetchall()
            
            return [dict(row) for row in rows]
        except Exception as e:
            return []
    
    # ==================== 索引维护 ====================
    
    def get_session_stats(self, session_id: str) -> Dict:
        """获取会话统计信息"""
        try:
            meta = self.conn.execute(
                "SELECT * FROM sessions_meta WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            
            if not meta:
                return {"error": "Session not found"}
            
            # FTS5 统计
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


# ==================== 模块级便捷函数（替代原 memory_tools.py 函数） ====================

# 全局单例（懒加载）
_db_instance = None

def _get_db() -> SessionDB:
    """获取全局 SessionDB 实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = SessionDB()
    return _db_instance


def save_session_history(messages: list, summary: str = None, session_id: str = None) -> str:
    """Save conversation history to SQLite (替代原 JSONL 实现)"""
    return _get_db().save_session_history(messages, summary, session_id)


def load_session_history(session_id: str) -> str:
    """Load conversation history from SQLite (替代原 JSONL 实现)"""
    return _get_db().load_session_history(session_id)


def list_sessions(limit: int = 10) -> str:
    """List recent sessions from SQLite (替代原 JSONL 实现)"""
    return _get_db().list_sessions(limit)


def search_history(keyword: str, limit: int = 20) -> str:
    """Search conversation history using FTS5 (替代原 JSONL 实现)"""
    return _get_db().search_history(keyword, limit)
