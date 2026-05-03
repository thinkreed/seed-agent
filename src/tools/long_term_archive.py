"""
L5 工作日志层 - FTS5 + LLM 自动摘要

核心功能:
1. 归档会话事件流到长期存储
2. LLM 自动生成核心结论摘要（写读书笔记）
3. FTS5 全文检索 + jieba 中文分词
4. 跨会话知识检索

特性:
- 每次长谈后自动总结
- 永久存储，支持语义搜索
- 提取关键发现
- 智能目录索引
"""

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)

try:
    import jieba

    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# 数据库路径
ARCHIVE_DB_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "archives.db"


# 导入 session_db 的分词缓存函数（延迟导入避免循环依赖）
def _get_tokenize_func():
    """延迟获取分词函数，避免模块加载时的循环依赖"""
    from src.tools.session_db import tokenize_for_fts5

    return tokenize_for_fts5


class LongTermArchiveLayer:
    """L5 工作日志 - FTS5 + LLM 摘要

    核心功能:
    1. archive_session(): 归档会话事件流
    2. search_with_context(): 语义搜索 + 摘要提取
    3. get_archive(): 获取完整归档
    4. get_archive_stats(): 归档统计

    数据库 Schema:
    - archives: 归档主表
    - archive_events: 事件详情表
    - archives_fts: FTS5 全文索引虚拟表
    """

    _instance: "LongTermArchiveLayer | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> "LongTermArchiveLayer":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self, db_path: str | Path | None = None, llm_gateway: "LLMGateway | None" = None
    ):
        with LongTermArchiveLayer._lock:
            if LongTermArchiveLayer._initialized:
                return
            LongTermArchiveLayer._initialized = True

        self.db_path = str(db_path or ARCHIVE_DB_PATH)
        self._llm_gateway = llm_gateway
        self.conn: sqlite3.Connection | None = None
        self._init_db()

    def set_llm_gateway(self, gateway: "LLMGateway") -> None:
        """设置 LLM Gateway（用于自动摘要）"""
        self._llm_gateway = gateway

    def _init_db(self) -> None:
        """初始化数据库连接和 Schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # 单例模式允许跨线程访问，使用 check_same_thread=False
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # 性能优化 PRAGMA
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")

        self._create_schema()

    def close(self) -> None:
        """关闭数据库连接"""
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.Error as e:
                logger.warning(f"Database close error: {type(e).__name__}: {e}")
            finally:
                self.conn = None
                LongTermArchiveLayer._instance = None
                LongTermArchiveLayer._initialized = False

    def _ensure_conn(self) -> sqlite3.Connection:
        """确保数据库连接可用"""
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn

    def _create_schema(self) -> None:
        """创建数据库 Schema"""
        cursor = self._ensure_conn().cursor()

        # 归档主表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archives (
                archive_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                summary TEXT,
                key_findings TEXT,
                events_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_archives_session ON archives(session_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_archives_created ON archives(created_at)"
        )

        # 事件详情表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archive_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_id TEXT NOT NULL,
                event_id INTEGER,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp REAL,
                FOREIGN KEY (archive_id) REFERENCES archives(archive_id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_archive ON archive_events(archive_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON archive_events(event_type)"
        )

        # FTS5 全文索引虚拟表
        # tokenize='unicode61 remove_diacritics 2' 支持中文
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS archives_fts USING fts5(
                archive_id,
                session_id,
                summary,
                key_findings,
                event_content,
                tokenize='unicode61 remove_diacritics 2',
                prefix='2 3 4'
            )
        """)

        self._ensure_conn().commit()

    # === 归档 ===

    async def archive_session(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """归档会话

        流程:
        1. LLM 生成核心结论摘要
        2. 存储到数据库
        3. FTS5 自动索引

        Args:
            session_id: 会话 ID
            events: 事件列表
            metadata: 可选元数据

        Returns:
            archive_id
        """
        if not events:
            return "Error: No events to archive"

        archive_id = f"archive_{session_id}_{int(time.time())}"
        created_at = datetime.now().isoformat()

        # 1. LLM 生成摘要
        summary = await self._generate_summary(events)
        key_findings = await self._extract_key_findings(events)

        # 2. 存储归档主记录
        key_findings_json = json.dumps(key_findings, ensure_ascii=False)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        self._ensure_conn().execute(
            """
            INSERT INTO archives
                (archive_id, session_id, summary, key_findings, events_count, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                archive_id,
                session_id,
                summary,
                key_findings_json,
                len(events),
                created_at,
                metadata_json,
            ),
        )

        # 3. 存储事件详情
        self._store_events(archive_id, events)

        # 4. 更新 FTS5 索引
        self._update_fts_index(archive_id, session_id, summary, key_findings, events)

        self._ensure_conn().commit()

        logger.info(f"Session archived: {archive_id} ({len(events)} events)")
        return archive_id

    async def archive_from_event_stream(
        self, event_stream: Any, metadata: dict[str, Any] | None = None
    ) -> str:
        """从 SessionEventStream 归档

        Args:
            event_stream: SessionEventStream 实例
            metadata: 可选元数据

        Returns:
            archive_id
        """
        events = event_stream.get_events()
        return await self.archive_session(event_stream.session_id, events, metadata)

    def _store_events(self, archive_id: str, events: list[dict[str, Any]]) -> None:
        """存储事件详情"""
        for event in events:
            event_data_json = json.dumps(event.get("data", {}), ensure_ascii=False)
            self._ensure_conn().execute(
                """
                INSERT INTO archive_events
                    (archive_id, event_id, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    archive_id,
                    event.get("id", 0),
                    event.get("type", "unknown"),
                    event_data_json,
                    event.get("timestamp", 0),
                ),
            )

    def _update_fts_index(
        self,
        archive_id: str,
        session_id: str,
        summary: str,
        key_findings: list[str],
        events: list[dict[str, Any]],
    ) -> None:
        """更新 FTS5 索引"""
        # 构建事件内容文本
        event_content = self._build_event_content_for_fts(events)
        key_findings_text = " ".join(key_findings)

        # 使用 tokenize_for_fts5 进行分词预处理（带缓存）
        tokenize = _get_tokenize_func()
        summary = tokenize(summary)
        key_findings_text = tokenize(key_findings_text)
        event_content = tokenize(event_content)

        self._ensure_conn().execute(
            """
            INSERT INTO archives_fts
                (archive_id, session_id, summary, key_findings, event_content)
            VALUES (?, ?, ?, ?, ?)
        """,
            (archive_id, session_id, summary, key_findings_text, event_content),
        )

    def _build_event_content_for_fts(self, events: list[dict[str, Any]]) -> str:
        """构建事件内容文本用于 FTS"""
        content_parts = []

        for event in events:
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            if event_type == "user_input":
                content_parts.append(event_data.get("content", ""))
            elif event_type == "llm_response":
                content_parts.append(event_data.get("content", "")[:500])
            elif event_type == "tool_result":
                content_parts.append(event_data.get("content", "")[:200])

        return " ".join(content_parts)

    async def _generate_summary(self, events: list[dict[str, Any]]) -> str:
        """LLM 生成核心结论摘要

        要求: 1-2 句话总结核心结论
        """
        # 构建对话历史
        history_text = self._format_events_for_summary(events)

        if not history_text:
            return "无内容摘要"

        if not self._llm_gateway:
            # 无 LLM Gateway，使用简单摘要
            return self._simple_summary(events)

        prompt = f"""请用1-2句话总结以下对话的核心结论，保留最有价值的信息:

{history_text[:2000]}

摘要格式:
- 核心结论: ...
"""

        try:
            result = await self._llm_gateway.chat_completion(
                model_id="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                priority=2,  # HIGH
            )

            return (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "摘要生成失败")
            )
        except Exception as e:
            logger.warning(f"LLM summary failed: {type(e).__name__}: {e}")
            return self._simple_summary(events)

    def _simple_summary(self, events: list[dict[str, Any]]) -> str:
        """简单摘要（无 LLM 时）"""
        user_inputs = [e for e in events if e.get("type") == "user_input"]

        if user_inputs:
            first_input = user_inputs[0].get("data", {}).get("content", "")[:100]
            return f"会话包含 {len(events)} 个事件，用户请求: {first_input}"

        return f"会话包含 {len(events)} 个事件"

    async def _extract_key_findings(self, events: list[dict[str, Any]]) -> list[str]:
        """提取关键发现"""
        history_text = self._format_events_for_summary(events)

        if not history_text:
            return []

        if not self._llm_gateway:
            # 无 LLM，使用简单提取
            return self._simple_findings(events)

        prompt = f"""从以下对话中提取3-5个关键发现:

{history_text[:2000]}

关键发现格式 (每行一个，简洁):
1. 发现内容
2. 发现内容
...
"""

        try:
            result = await self._llm_gateway.chat_completion(
                model_id="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                priority=2,  # HIGH
            )

            response = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            findings = [line.strip() for line in response.split("\n") if line.strip()]
            return findings[:5]
        except Exception as e:
            logger.warning(f"LLM findings extraction failed: {type(e).__name__}: {e}")
            return self._simple_findings(events)

    def _simple_findings(self, events: list[dict[str, Any]]) -> list[str]:
        """简单发现提取"""
        findings = []

        # 提取工具调用
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        if tool_events:
            tools_used = set()
            for e in tool_events:
                tool_name = e.get("data", {}).get("function", {}).get("name", "unknown")
                tools_used.add(tool_name)
            findings.append(f"使用了工具: {', '.join(tools_used)}")

        # 提取错误
        error_events = [e for e in events if e.get("type") == "error_occurred"]
        if error_events:
            findings.append(f"发生了 {len(error_events)} 个错误")

        return findings

    def _format_events_for_summary(self, events: list[dict[str, Any]]) -> str:
        """格式化事件用于摘要"""
        lines = []

        for event in events:
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            if event_type == "user_input":
                lines.append(f"用户: {event_data.get('content', '')[:200]}")
            elif event_type == "llm_response":
                content = event_data.get("content", "")
                if content:
                    lines.append(f"助手: {content[:300]}")
            elif event_type == "tool_call":
                tool_name = event_data.get("function", {}).get("name", "unknown")
                lines.append(f"调用工具: {tool_name}")
            elif event_type == "tool_result":
                lines.append(f"工具结果: {event_data.get('content', '')[:100]}")

        return chr(10).join(lines)

    # === 搜索 ===

    def search_with_context(
        self, keyword: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """语义搜索 + 摘要提取

        Args:
            keyword: 搜索关键词
            limit: 结果限制

        Returns:
            [{
                "archive_id": "...",
                "session_id": "...",
                "summary": "核心结论摘要",
                "matched_snippet": "匹配片段",
                "key_findings": ["发现1", "发现2"],
                "timestamp": "...",
                "relevance_score": 0.XX
            }]
        """
        # FTS5 搜索
        fts_query = self._sanitize_fts_query(keyword)
        if not fts_query:
            return []

        try:
            rows = (
                self._ensure_conn()
                .execute(
                    """
                SELECT
                    a.archive_id,
                    a.session_id,
                    a.summary,
                    a.key_findings,
                    a.created_at,
                    fts.event_content as matched_content
                FROM archives a
                JOIN archives_fts fts ON a.archive_id = fts.archive_id
                WHERE archives_fts MATCH ?
                ORDER BY a.created_at DESC
                LIMIT ?
            """,
                    (fts_query, limit),
                )
                .fetchall()
            )

            results = []
            for row in rows:
                key_findings = json.loads(row["key_findings"] or "[]")
                matched_snippet = self._extract_matched_snippet(
                    row["matched_content"] or "", keyword
                )

                results.append(
                    {
                        "archive_id": row["archive_id"],
                        "session_id": row["session_id"],
                        "summary": row["summary"],
                        "matched_snippet": matched_snippet,
                        "key_findings": key_findings,
                        "timestamp": row["created_at"],
                        "relevance_score": 1.0,  # FTS5 不返回分数
                    }
                )

            return results
        except sqlite3.Error as e:
            logger.warning(f"FTS search failed: {type(e).__name__}: {e}")
            return []

    def _sanitize_fts_query(self, query: str) -> str:
        """清理 FTS5 查询字符串"""
        if not query:
            return ""

        # 限制长度
        if len(query) > 200:
            query = query[:200]

        # 使用 tokenize_for_fts5 进行分词（带缓存）
        tokenize = _get_tokenize_func()
        query = tokenize(query)

        # 移除 FTS5 特殊字符
        special_chars = '"():*^#&|-!~'
        for char in special_chars:
            query = query.replace(char, "")

        # 移除 FTS5 关键字
        keywords = ["AND", "OR", "NOT", "NEAR", "ORDER", "BY", "LIMIT", "OFFSET"]
        for kw in keywords:
            query = query.replace(kw, "")

        return query.strip()

    def _extract_matched_snippet(self, content: str, keyword: str) -> str:
        """提取匹配片段"""
        if not content:
            return ""

        keyword_lower = keyword.lower()
        content_lower = content.lower()

        idx = content_lower.find(keyword_lower)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(content), idx + len(keyword) + 50)
            return content[start:end]

        return content[:100]

    def search_by_time_range(
        self, start_time: str, end_time: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """时间范围搜索

        Args:
            start_time: ISO 格式开始时间
            end_time: ISO 格式结束时间
            limit: 结果限制

        Returns:
            归档列表
        """
        rows = (
            self._ensure_conn()
            .execute(
                """
            SELECT archive_id, session_id, summary, key_findings, created_at, events_count
            FROM archives
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
                (start_time, end_time, limit),
            )
            .fetchall()
        )

        results = []
        for row in rows:
            results.append(
                {
                    "archive_id": row["archive_id"],
                    "session_id": row["session_id"],
                    "summary": row["summary"],
                    "key_findings": json.loads(row["key_findings"] or "[]"),
                    "timestamp": row["created_at"],
                    "events_count": row["events_count"],
                }
            )

        return results

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        """获取完整归档"""
        row = (
            self._ensure_conn()
            .execute(
                """
            SELECT archive_id, session_id, summary, key_findings, created_at, events_count, metadata
            FROM archives
            WHERE archive_id = ?
        """,
                (archive_id,),
            )
            .fetchone()
        )

        if not row:
            return None

        # 获取事件详情
        event_rows = (
            self._ensure_conn()
            .execute(
                """
            SELECT event_id, event_type, event_data, timestamp
            FROM archive_events
            WHERE archive_id = ?
            ORDER BY event_id
        """,
                (archive_id,),
            )
            .fetchall()
        )

        events = []
        for er in event_rows:
            events.append(
                {
                    "id": er["event_id"],
                    "type": er["event_type"],
                    "data": json.loads(er["event_data"] or "{}"),
                    "timestamp": er["timestamp"],
                }
            )

        return {
            "archive_id": row["archive_id"],
            "session_id": row["session_id"],
            "summary": row["summary"],
            "key_findings": json.loads(row["key_findings"] or "[]"),
            "created_at": row["created_at"],
            "events_count": row["events_count"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "events": events,
        }

    def get_archives_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的所有归档"""
        rows = (
            self._ensure_conn()
            .execute(
                """
            SELECT archive_id, session_id, summary, created_at, events_count
            FROM archives
            WHERE session_id = ?
            ORDER BY created_at DESC
        """,
                (session_id,),
            )
            .fetchall()
        )

        return [dict(row) for row in rows]

    # === 统计 ===

    def get_archive_stats(self) -> dict[str, Any]:
        """获取归档统计"""
        total_archives = (
            self._ensure_conn()
            .execute("SELECT COUNT(*) as count FROM archives")
            .fetchone()["count"]
        )

        total_events = (
            self._ensure_conn()
            .execute("SELECT COUNT(*) as count FROM archive_events")
            .fetchone()["count"]
        )

        avg_events = (
            self._ensure_conn()
            .execute("""
            SELECT AVG(events_count) as avg FROM archives WHERE events_count > 0
        """)
            .fetchone()["avg"]
            or 0
        )

        recent_archives = (
            self._ensure_conn()
            .execute("""
            SELECT archive_id, session_id, summary, created_at, events_count
            FROM archives
            ORDER BY created_at DESC
            LIMIT 5
        """)
            .fetchall()
        )

        return {
            "total_archives": total_archives,
            "total_events": total_events,
            "avg_events_per_archive": round(avg_events, 2),
            "recent_archives": [dict(row) for row in recent_archives],
        }

    def delete_archive(self, archive_id: str) -> str:
        """删除归档"""
        # 删除事件
        self._ensure_conn().execute(
            "DELETE FROM archive_events WHERE archive_id = ?", (archive_id,)
        )

        # 删除 FTS 索引
        self._ensure_conn().execute(
            "DELETE FROM archives_fts WHERE archive_id = ?", (archive_id,)
        )

        # 删除归档记录
        self._ensure_conn().execute(
            "DELETE FROM archives WHERE archive_id = ?", (archive_id,)
        )

        self._ensure_conn().commit()
        return f"Archive deleted: {archive_id}"

    def cleanup_old_archives(
        self, max_age_days: int = 90, keep_count: int = 100
    ) -> int:
        """清理旧归档

        Args:
            max_age_days: 最大保留天数（超过此天数的归档优先删除）
            keep_count: 最少保留数量（即使超过天数也保留此数量）

        Returns:
            清理的归档数量
        """
        import datetime as dt_module

        cutoff_date = dt_module.datetime.now() - dt_module.timedelta(days=max_age_days)
        cutoff_str = cutoff_date.isoformat()

        # 检查总数
        total = (
            self._ensure_conn()
            .execute("SELECT COUNT(*) as count FROM archives")
            .fetchone()["count"]
        )

        if total <= keep_count:
            return 0

        # 计算需要删除的数量
        to_delete = total - keep_count

        # 优先删除超过天数的旧归档
        rows = (
            self._ensure_conn()
            .execute(
                """
            SELECT archive_id FROM archives
            WHERE created_at < ?
            ORDER BY created_at ASC
            LIMIT ?
        """,
                (cutoff_str, to_delete),
            )
            .fetchall()
        )

        # 如果删除数量不足，继续删除最旧的归档（确保保留 keep_count）
        deleted_count = len(rows)
        if deleted_count < to_delete:
            remaining_to_delete = to_delete - deleted_count
            # 排除已删除的，继续删除最旧的
            already_deleted_ids = [row["archive_id"] for row in rows]
            if already_deleted_ids:
                placeholders = ",".join("?" * len(already_deleted_ids))
                # S608: 使用参数化查询，placeholders 只是占位符，值通过参数传递
                additional_rows = (
                    self._ensure_conn()
                    .execute(
                        f"SELECT archive_id FROM archives WHERE archive_id NOT IN ({placeholders}) ORDER BY created_at ASC LIMIT ?",  # noqa: S608
                        (*already_deleted_ids, remaining_to_delete),
                    )
                    .fetchall()
                )
            else:
                additional_rows = (
                    self._ensure_conn()
                    .execute(
                        "SELECT archive_id FROM archives ORDER BY created_at ASC LIMIT ?",
                        (remaining_to_delete,),
                    )
                    .fetchall()
                )
            rows = list(rows) + list(additional_rows)

        for row in rows:
            self.delete_archive(row["archive_id"])

        logger.info(f"Cleaned up {len(rows)} old archives")
        return len(rows)

    # === 摘要标记同步 ===

    def sync_summary_markers(self, event_stream: Any) -> str:
        """从事件流同步摘要标记

        Args:
            event_stream: SessionEventStream 实例

        Returns:
            同步结果
        """
        # 获取最近的摘要标记
        last_marker = event_stream.find_last_summary_marker()

        if not last_marker:
            return "No summary marker found"

        marker_data = last_marker.get("data", {})
        summary = marker_data.get("summary", "")

        if not summary:
            return "Empty summary in marker"

        # 更新归档摘要（如果已存在）
        session_id = event_stream.session_id
        archives = self.get_archives_by_session(session_id)

        if archives:
            # 更新最近归档的摘要
            latest_archive_id = archives[0]["archive_id"]
            self._ensure_conn().execute(
                """
                UPDATE archives SET summary = ? WHERE archive_id = ?
            """,
                (summary, latest_archive_id),
            )

            # 更新 FTS 索引
            summary_tokens = " ".join(jieba.cut(summary)) if _HAS_JIEBA else summary

            self._ensure_conn().execute(
                """
                UPDATE archives_fts SET summary = ? WHERE archive_id = ?
            """,
                (summary_tokens, latest_archive_id),
            )

            self._ensure_conn().commit()
            return f"Summary synced for archive: {latest_archive_id}"

        return "No archive found for session"
