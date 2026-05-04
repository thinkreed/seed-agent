"""
L4 Session 数据库存储层 (SQLite + FTS5)
替代原有的 JSONL 文件存储，支持中文全文搜索

使用 jieba 进行中文分词预处理，通过 FTS5 实现高效搜索。

Memory Graph 增强:
- gene_outcomes 表: 存储 Skill 执行结果
- FTS5 虚拟表: 信号模式全文搜索
- 选择算法支持: 成功率统计、禁用阈值、Laplace 平滑
"""

import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

try:
    import jieba

    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# 使用共享配置模块
try:
    from src.shared_config import get_memory_graph_config

    _config = get_memory_graph_config()
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": _config.half_life_days,
        "ban_threshold": _config.ban_threshold,
        "min_attempts_for_ban": _config.min_attempts_for_ban,
        "memory_weight": _config.memory_weight,
        "trigger_weight": _config.trigger_weight,
        "cold_start_penalty": _config.cold_start_penalty,
        "recent_boost_factor": _config.recent_boost_factor,
        "recent_days": _config.recent_days,
        "max_entries_per_skill": _config.max_entries_per_skill,
    }
except ImportError:
    # Fallback: 使用默认值（避免循环导入问题）
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": 30,
        "ban_threshold": 0.18,
        "min_attempts_for_ban": 2,
        "memory_weight": 0.6,
        "trigger_weight": 0.4,
        "cold_start_penalty": 0.5,
        "recent_boost_factor": 0.2,
        "recent_days": 30,
        "max_entries_per_skill": 5000,
    }

# 数据库路径
DB_PATH = Path.home() / ".seed" / "memory" / "raw" / "sessions.db"


# LRU 缓存配置
_MAX_CACHE_TEXT_LENGTH = 1000  # 提高缓存阈值，覆盖更多常见查询
_CACHE_MAXSIZE = 2000  # 增加缓存容量，减少重复分词


def tokenize_for_fts5(text: str) -> str:
    """
    中文分词预处理（带缓存）
    - 如果有 jieba，使用 jieba 分词
    - 否则 fallback 到 unicode61（单字符）
    - 使用 LRU 缓存避免重复分词开销
    - 长文本不缓存，避免内存占用过多
    - 空字符串直接返回，避免无意义处理
    """
    if not text:
        return ""

    # 长文本不缓存，直接分词
    if len(text) > _MAX_CACHE_TEXT_LENGTH:
        if _HAS_JIEBA:
            tokens = jieba.cut(text)
            return " ".join(tokens)
        return text

    # 短文本使用缓存
    return _tokenize_cached(text)


@lru_cache(maxsize=_CACHE_MAXSIZE)
def _tokenize_cached(text: str) -> str:
    """缓存版本的分词函数，仅用于短文本"""
    if _HAS_JIEBA:
        tokens = jieba.cut(text)
        return " ".join(tokens)
    return text


# 预编译翻译表：一次性移除所有 FTS5 特殊字符和 Unicode 特殊字符
# 性能优化：避免循环替换 21 次（11 FTS + 10 Unicode）
_FTS_SPECIAL_CHARS = '"():*^#&|-!~'
_UNICODE_SPECIAL_CHARS = "\u200b\u200c\u200d\u00ad\u2060\u2061\u2062\u2063\u2064\ufeff"
_FTS_SANITIZE_TABLE = str.maketrans("", "", _FTS_SPECIAL_CHARS + _UNICODE_SPECIAL_CHARS)

# 预编译 FTS5 关键字正则表达式
_FTS_KEYWORDS_PATTERN = re.compile(
    r"\b(?:AND|OR|NOT|NEAR|ORDER|BY|LIMIT|OFFSET)\b", flags=re.IGNORECASE
)


def _sanitize_fts_query(query: str) -> str:
    """
    清理 FTS5 查询字符串，防止语法错误和注入攻击。

    FTS5 特殊字符: " & | ( ) - : * ^ #
    防护措施:
    1. 分词后移除所有特殊字符（使用 str.translate 一次性处理）
    2. 限制查询长度防止 DoS
    3. 禁止 FTS5 特殊语法（column:, NEAR, NOT, AND, OR）
    4. 仅保留安全的单词匹配
    5. 处理 Unicode 特殊字符
    """
    if not query:
        return ""

    # 限制查询长度防止 DoS
    if len(query) > 200:
        query = query[:200]
        logger.warning("FTS query truncated to 200 chars for security")

    # 分词处理
    if _HAS_JIEBA:
        tokens = jieba.cut(query)
        query = " ".join(tokens)

    # 一次性移除所有特殊字符（性能优化）
    query = query.translate(_FTS_SANITIZE_TABLE)

    # 禁止 FTS5 关键字（预编译正则）
    query = _FTS_KEYWORDS_PATTERN.sub("", query)

    # 移除数字开头的 token（FTS5 可能解析为 column filter）
    tokens = query.split()
    safe_tokens = [
        t for t in tokens if not t.isdigit() and len(t) > 0 and not t[0].isdigit()
    ]
    query = " ".join(safe_tokens)

    return query.strip()


# 公共导出别名（供其他模块复用）
sanitize_fts_query = _sanitize_fts_query


class BannedSkillInfo(TypedDict):
    """禁用 Skill 信息类型定义"""

    skill_name: str
    total_attempts: int
    current_value: float
    success_rate: float
    laplace_rate: float
    last_time: str
    ban_reason: str
    suggested_action: str


class SessionDB:
    """Session 数据库管理类 (SQLite + FTS5 + Memory Graph)

    支持上下文管理器协议，确保资源正确释放。
    使用单例模式防止多连接资源泄漏。
    使用线程锁保证多线程环境下的线程安全。
    """

    _instance: "SessionDB | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()  # 单例创建锁

    def __new__(cls, db_path: str | None = None) -> "SessionDB":
        """单例模式：确保全局只有一个 SessionDB 实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                # 双重检查锁定模式，避免不必要的锁开销
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str | None = None):
        # 使用类锁保护初始化状态检查
        with SessionDB._lock:
            if SessionDB._initialized:
                return
            SessionDB._initialized = True

        self.db_path = db_path or str(DB_PATH)
        self.conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self):
        """初始化数据库连接和 Schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # 性能优化 PRAGMA（初始化时直接使用 self.conn）
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-32000;")

        self._create_schema()

    def close(self) -> None:
        """关闭数据库连接，释放资源并重置单例状态"""
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.OperationalError as e:
                logger.warning(f"Database operational error on close: {e}")
            except sqlite3.Error as e:
                logger.warning(f"Database error on close: {type(e).__name__}: {e}")
            finally:
                self.conn = None
                # 重置单例状态，允许重新初始化
                SessionDB._instance = None
                SessionDB._initialized = False

    def __enter__(self) -> "SessionDB":
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器退出，确保连接关闭"""
        self.close()

    def _ensure_conn(self) -> sqlite3.Connection:
        """确保数据库连接可用"""
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn

    def _create_schema(self):
        """创建数据库 Schema"""
        self._create_session_messages_schema()
        self._create_sessions_meta_schema()
        self._create_gene_outcomes_schema()
        self._create_gene_outcomes_triggers()
        self._create_gene_outcomes_indexes()
        self._ensure_conn().commit()

    def _create_session_messages_schema(self):
        """创建 session_messages 表和索引"""
        cursor = self._ensure_conn().cursor()
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
        for idx in ["session_id", "timestamp", "role"]:
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_session_messages_{idx} ON session_messages({idx})"
            )
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts
            USING fts5(content, session_id, role,
                tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')
        """)

    def _create_sessions_meta_schema(self):
        """创建 sessions_meta 表和索引"""
        cursor = self._ensure_conn().cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions_meta (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                last_updated TEXT,
                message_count INTEGER DEFAULT 0,
                summary TEXT
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_meta_created ON sessions_meta(created_at)"
        )

    def _create_gene_outcomes_schema(self):
        """创建 gene_outcomes 表和 FTS5 虚拟表"""
        cursor = self._ensure_conn().cursor()
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
        cursor = self._ensure_conn().cursor()
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
        cursor = self._ensure_conn().cursor()
        for col in ["skill_name", "timestamp", "outcome_status", "session_id"]:
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_gene_{col} ON gene_outcomes({col})"
            )

        # 复合索引：优化近期统计查询 (skill_name + timestamp)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gene_skill_time ON gene_outcomes(skill_name, timestamp)"
        )

        self._ensure_conn().commit()

    def _parse_tool_calls(self, tool_calls) -> str | None:
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
        signals: list[str] | None = None,
        session_id: str | None = None,
        context: str | None = None,
        intent: str | None = None,
        blast_radius: dict | None = None,
    ) -> str:
        """记录 Skill 执行结果到 gene_outcomes 表"""
        if outcome not in ("success", "failed", "partial"):
            return f"Invalid outcome status: {outcome}"
        if not (0.0 <= score <= 1.0):
            return f"Invalid score: {score} (must be 0.0-1.0)"

        signal_pattern = " ".join(signals) if signals else ""
        timestamp = datetime.now().isoformat()
        blast_radius_json = json.dumps(blast_radius) if blast_radius else None

        try:
            self._execute_skill_outcome_insert(
                skill_name,
                signal_pattern,
                outcome,
                score,
                session_id,
                timestamp,
                context,
                intent,
                blast_radius_json,
            )
            stats = self.get_skill_stats(skill_name)
            return (
                f"Outcome recorded: {skill_name} -> {outcome} "
                f"(score: {score}). Stats: {stats['total']} total, "
                f"{stats['success_rate']:.1%} success"
            )
        except sqlite3.IntegrityError:
            return f"Duplicate outcome ignored: {skill_name} at {timestamp}"
        except Exception as e:
            return f"Error recording outcome: {e!s}"

    def _execute_skill_outcome_insert(
        self,
        skill_name,
        signal_pattern,
        outcome,
        score,
        session_id,
        timestamp,
        context,
        intent,
        blast_radius_json,
    ):
        """执行 Skill 结果插入"""
        self._ensure_conn().execute(
            """
            INSERT INTO gene_outcomes
                (skill_name, signal_pattern, outcome_status, outcome_score,
                 session_id, timestamp, iteration_context, intent, blast_radius)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                skill_name,
                signal_pattern,
                outcome,
                score,
                session_id,
                timestamp,
                context,
                intent,
                blast_radius_json,
            ),
        )
        self._ensure_conn().commit()

    def _get_skill_basic_stats(self, skill_name: str) -> dict:
        """获取 Skill 基础统计信息"""
        row = (
            self._ensure_conn()
            .execute(
                """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN outcome_status = 'failed' THEN 1 ELSE 0 END) as failures,
                MAX(CASE WHEN outcome_status = 'success' THEN timestamp ELSE NULL END) as last_success,
                MAX(CASE WHEN outcome_status = 'failed' THEN timestamp ELSE NULL END) as last_failure,
                AVG(outcome_score) as avg_score
            FROM gene_outcomes
            WHERE skill_name = ?
        """,
                (skill_name,),
            )
            .fetchone()
        )
        return dict(row) if row else {}

    def _get_skill_recent_stats(self, skill_name: str, recent_days: int = 30) -> dict:
        """获取 Skill 近期统计信息 (最近 N 天)"""
        recent_row = (
            self._ensure_conn()
            .execute(
                """
            SELECT
                COUNT(*) as recent_total,
                SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as recent_successes
            FROM gene_outcomes
            WHERE skill_name = ? AND timestamp > datetime('now', ?)
        """,
                (skill_name, f"-{recent_days} days"),
            )
            .fetchone()
        )
        return dict(recent_row) if recent_row else {}

    def _compute_ban_status(
        self, skill_name: str, total: int, selection_value: float
    ) -> bool:
        """检查 Skill 是否应被禁用"""
        min_attempts = MEMORY_GRAPH_CONFIG["min_attempts_for_ban"]
        ban_threshold = MEMORY_GRAPH_CONFIG["ban_threshold"]
        return total >= min_attempts and selection_value < ban_threshold

    def get_skill_stats(self, skill_name: str) -> dict:
        """获取 Skill 的聚合统计信息"""
        try:
            row = self._get_skill_basic_stats(skill_name)
            if not row or row.get("total", 0) == 0:
                return self._get_default_stats()

            total = row["total"]
            successes = row["successes"]
            failures = row["failures"]

            # 传递 basic_stats 避免 N+1 查询
            rates = self._calculate_rates(skill_name, successes, total, basic_stats=row)
            return {
                "total": total,
                "successes": successes,
                "failures": failures,
                "success_rate": rates["success_rate"],
                "laplace_rate": rates["laplace_rate"],
                "recent_success_rate": rates["recent_success_rate"],
                "last_success": row["last_success"],
                "last_failure": row["last_failure"],
                "avg_score": row["avg_score"],
                "is_banned": rates["is_banned"],
                "selection_value": rates["selection_value"],
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_default_stats(self) -> dict:
        """返回冷启动默认统计"""
        return {
            "total": 0,
            "successes": 0,
            "failures": 0,
            "success_rate": 0.0,
            "recent_success_rate": 0.0,
            "last_success": None,
            "last_failure": None,
            "is_banned": False,
            "selection_value": 0.0,
            "laplace_rate": 0.5,
        }

    def _calculate_rates(
        self,
        skill_name: str,
        successes: int,
        total: int,
        basic_stats: dict | None = None,
    ) -> dict:
        """计算各种分数和状态

        Args:
            skill_name: Skill 名称
            successes: 成功次数
            total: 总次数
            basic_stats: 基础统计信息（可选，用于避免重复查询）
        """
        success_rate = successes / total if total > 0 else 0.0
        laplace_rate = (successes + 1) / (total + 2)

        recent_days: int = MEMORY_GRAPH_CONFIG["recent_days"]  # type: ignore[assignment]
        recent_row = self._get_skill_recent_stats(skill_name, recent_days)
        recent_success_rate = 0.0
        if recent_row and recent_row.get("recent_total", 0) > 0:
            recent_success_rate = (
                recent_row["recent_successes"] / recent_row["recent_total"]
            )

        # 使用传入的 basic_stats 避免 N+1 查询
        last_timestamp = basic_stats.get("last_success") if basic_stats else None
        selection_value = self._compute_selection_value_with_timestamp(
            successes, total, recent_success_rate, last_timestamp
        )
        is_banned = self._compute_ban_status(skill_name, total, selection_value)

        return {
            "success_rate": success_rate,
            "laplace_rate": laplace_rate,
            "recent_success_rate": recent_success_rate,
            "selection_value": selection_value,
            "is_banned": is_banned,
        }

    def _compute_selection_value_with_timestamp(
        self,
        successes: int,
        total: int,
        recent_success_rate: float,
        last_timestamp: str | None = None,
    ) -> float:
        """
        计算选择分数 (GEP-style) - 使用传入的时间戳避免重复查询

        公式: value = laplace_rate * decay_weight + recent_boost
        """
        half_life = MEMORY_GRAPH_CONFIG["half_life_days"]
        recent_boost_factor = MEMORY_GRAPH_CONFIG["recent_boost_factor"]

        # Laplace 平滑概率
        p = (successes + 1) / (total + 2)

        # 计算衰减权重（使用传入的时间戳）
        decay_weight = 1.0
        if last_timestamp:
            try:
                last_time = datetime.fromisoformat(last_timestamp)
                age_days = (datetime.now() - last_time).days
                decay_weight = 0.5 ** (age_days / half_life)
            except Exception as e:
                logger.debug(f"Decay calculation failed: {type(e).__name__}")
                decay_weight = 1.0

        # 近期成功加成
        recent_boost = recent_success_rate * recent_boost_factor

        return p * decay_weight + recent_boost

    def list_banned_skills(self) -> list[BannedSkillInfo]:
        """
        列出被禁用的 Skill（低于 ban_threshold）（批量查询优化，避免 N+1）

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
        min_attempts = MEMORY_GRAPH_CONFIG["min_attempts_for_ban"]
        ban_threshold = MEMORY_GRAPH_CONFIG["ban_threshold"]

        try:
            # 单次批量查询：计算所有 skill 的统计数据
            rows = (
                self._ensure_conn()
                .execute(
                    """
                SELECT
                    skill_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
                    MAX(timestamp) as last_time,
                    AVG(outcome_score) as avg_score
                FROM gene_outcomes
                GROUP BY skill_name
                HAVING COUNT(*) >= ?
            """,
                    (min_attempts,),
                )
                .fetchall()
            )

            banned: list[BannedSkillInfo] = []
            for row in rows:
                skill_name = row["skill_name"]
                total = row["total"]
                successes = row["successes"]

                # 计算统计数据（避免调用 get_skill_stats）
                success_rate = successes / total if total > 0 else 0.0
                laplace_rate = (successes + 1) / (total + 2)
                selection_value = laplace_rate

                if selection_value < ban_threshold:
                    banned.append(
                        {
                            "skill_name": skill_name,
                            "total_attempts": total,
                            "current_value": selection_value,
                            "success_rate": success_rate,
                            "laplace_rate": laplace_rate,
                            "last_time": row["last_time"],
                            "ban_reason": "Low success rate",
                            "suggested_action": "Review strategy or retire",
                        }
                    )

            return banned
        except Exception as e:
            logger.warning(f"Failed to list banned skills: {type(e).__name__}: {e}")
            return []

    def get_top_skills(self, limit: int = 10) -> list[dict]:
        """
        获取成功率最高的 Skill（批量查询优化，避免 N+1）

        Returns:
            按 selection_value 排序的 Skill 列表
        """
        try:
            # 单次批量查询：计算所有 skill 的统计数据
            rows = (
                self._ensure_conn()
                .execute("""
                SELECT
                    skill_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes
                FROM gene_outcomes
                GROUP BY skill_name
                HAVING COUNT(*) > 0
            """)
                .fetchall()
            )

            skill_values = []
            for row in rows:
                skill_name = row["skill_name"]
                total = row["total"]
                successes = row["successes"]

                # 计算统计数据（避免调用 get_skill_stats）
                success_rate = successes / total if total > 0 else 0.0
                laplace_rate = (successes + 1) / (total + 2)
                selection_value = laplace_rate

                skill_values.append(
                    {
                        "skill_name": skill_name,
                        "selection_value": selection_value,
                        "success_rate": success_rate,
                        "total": total,
                    }
                )

            # 按选择分数排序
            skill_values.sort(key=lambda x: x["selection_value"], reverse=True)
            return skill_values[:limit]
        except Exception as e:
            logger.warning(f"Failed to get top skills: {type(e).__name__}: {e}")
            return []

    def search_outcomes_by_signal(self, signal: str, limit: int = 20) -> list[dict]:
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

            rows = (
                self._ensure_conn()
                .execute(
                    """
                SELECT
                    g.id, g.skill_name, g.signal_pattern, g.outcome_status, g.outcome_score, g.timestamp
                FROM gene_outcomes g
                JOIN gene_outcomes_fts fts ON g.id = fts.rowid
                WHERE gene_outcomes_fts MATCH ?
                ORDER BY g.timestamp DESC
                LIMIT ?
            """,
                    (fts_query, limit),
                )
                .fetchall()
            )

            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Failed to get context messages: {type(e).__name__}: {e}")
            return []

    def cleanup_old_outcomes(self, max_entries_per_skill: int | None = None) -> int:
        """
        清理过旧的执行记录 (FIFO)

        Args:
            max_entries_per_skill: 每个 Skill 最大保留记录数

        Returns:
            清理的记录总数
        """
        max_entries = (
            max_entries_per_skill or MEMORY_GRAPH_CONFIG["max_entries_per_skill"]
        )
        total_deleted = 0

        try:
            # 找出超限的 Skill
            rows = (
                self._ensure_conn()
                .execute(
                    """
                SELECT skill_name, COUNT(*) as count
                FROM gene_outcomes
                GROUP BY skill_name
                HAVING COUNT(*) > ?
            """,
                    (max_entries,),
                )
                .fetchall()
            )

            for row in rows:
                skill_name = row["skill_name"]
                excess = row["count"] - max_entries

                # 删除最旧的记录
                cursor = self._ensure_conn().execute(
                    """
                    DELETE FROM gene_outcomes
                    WHERE skill_name = ? AND id IN (
                        SELECT id FROM gene_outcomes
                        WHERE skill_name = ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                """,
                    (skill_name, skill_name, excess),
                )
                total_deleted += cursor.rowcount

            self._ensure_conn().commit()
            if total_deleted > 0:
                logger.info(
                    f"Cleanup completed: deleted {total_deleted} records from {len(rows)} skills"
                )
            return total_deleted
        except sqlite3.OperationalError as e:
            logger.error(
                f"Database operational error during cleanup: {type(e).__name__}: {e}"
            )
            return 0
        except sqlite3.IntegrityError as e:
            logger.error(
                f"Database integrity error during cleanup: {type(e).__name__}: {e}"
            )
            return 0
        except Exception as e:
            logger.error(
                f"Unexpected error during cleanup: {type(e).__name__}: {e}",
                exc_info=True,
            )
            return 0

    # ==================== 原有 Session 方法 ====================

    def _build_message_batches(
        self, messages: list[dict], session_id: str, now: str
    ) -> tuple[list[tuple], list[tuple]]:
        """构建消息批次 (session_messages + FTS)"""
        batch = []
        fts_batch = []
        for msg in messages:
            ts = msg.get("timestamp", now)
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = self._parse_tool_calls(msg.get("tool_calls"))
            tool_call_id = msg.get("tool_call_id")

            batch.append(
                (session_id, ts, role, content, tool_calls, tool_call_id, "message")
            )
            tokenized = tokenize_for_fts5(content) if content else ""
            fts_batch.append((session_id, tokenized, role))
        return batch, fts_batch

    def _insert_fts_index(self, cursor, fts_batch: list[tuple], start_id: int):
        """插入 FTS 索引 - 使用批量插入优化"""
        if not fts_batch:
            return

        # 构建批量数据
        batch_data = []
        for i, (sid, tokenized, role) in enumerate(fts_batch):
            rowid = start_id + i
            batch_data.append((rowid, tokenized, sid, role))

        # 执行批量插入
        cursor.executemany(
            "INSERT INTO session_messages_fts(rowid, content, session_id, role) VALUES (?, ?, ?, ?)",
            batch_data,
        )

    def _upsert_session_meta(
        self,
        cursor,
        session_id: str,
        now: str,
        msg_count: int,
        summary: str | None,
        is_new: bool,
    ):
        """插入或更新会话元数据"""
        if is_new:
            cursor.execute(
                "INSERT INTO sessions_meta "
                "(session_id, created_at, last_updated, message_count, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, now, now, msg_count, summary),
            )
        else:
            cursor.execute(
                "UPDATE sessions_meta SET last_updated = ?, "
                "message_count = message_count + ?, "
                "summary = COALESCE(?, summary) WHERE session_id = ?",
                (now, msg_count, summary, session_id),
            )

    def save_session_history(
        self,
        messages: list[dict],
        summary: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """保存会话历史到 SQLite"""
        try:
            if not session_id:
                session_id = self._generate_session_filename()

            now = datetime.now().isoformat()

            existing = (
                self._ensure_conn()
                .execute(
                    "SELECT session_id FROM sessions_meta WHERE session_id = ?",
                    (session_id,),
                )
                .fetchone()
            )
            is_new = existing is None

            cursor = self._ensure_conn().cursor()
            batch, fts_batch = self._build_message_batches(messages, session_id, now)

            cursor.executemany(
                "INSERT INTO session_messages "
                "(session_id, timestamp, role, content, tool_calls_json, "
                " tool_call_id, message_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                batch,
            )

            if batch:
                # executemany doesn't set lastrowid, so query for it
                start_id = (
                    cursor.execute("SELECT MAX(id) FROM session_messages").fetchone()[0]
                    - len(batch)
                    + 1
                )
                self._insert_fts_index(cursor, fts_batch, start_id)

            msg_count = len(messages)
            self._upsert_session_meta(
                cursor, session_id, now, msg_count, summary, is_new
            )

            self._ensure_conn().commit()
            return f"Session saved: {session_id} ({msg_count} messages)"
        except sqlite3.OperationalError as e:
            self._ensure_conn().rollback()
            logger.error(f"Database operational error saving session: {e}")
            return f"Error saving session (database issue): {e!s}"
        except sqlite3.IntegrityError as e:
            self._ensure_conn().rollback()
            logger.error(f"Database integrity error saving session: {e}")
            return f"Error saving session (integrity issue): {e!s}"
        except Exception as e:
            self._ensure_conn().rollback()
            logger.error(
                f"Unexpected error saving session: {type(e).__name__}: {e}",
                exc_info=True,
            )
            return f"Error saving session: {type(e).__name__}: {e!s}"

    def load_session_history(self, session_id: str) -> str:
        """从 SQLite 加载指定会话"""
        try:
            row = self._find_session(session_id)
            if not row:
                return f"Session not found: {session_id}"

            actual_id = row["session_id"]
            msg_count = row["message_count"]
            summary = row["summary"] if "summary" in row else None

            messages = (
                self._ensure_conn()
                .execute(
                    """
                SELECT role, content, tool_calls_json, tool_call_id
                FROM session_messages
                WHERE session_id = ? AND message_type = 'message'
                ORDER BY id ASC
            """,
                    (actual_id,),
                )
                .fetchall()
            )

            output = f"Session: {actual_id}\n"
            output += f"Created: {row['created_at']}\n"
            output += f"Messages: {msg_count}\n"
            if summary:
                output += f"Summary: {summary}\n"
            output += "---\n"

            for msg in messages:
                output += self._format_session_message(msg) + "\n"

            return output
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error loading session: {e}")
            return f"Error loading session (database issue): {e!s}"
        except Exception as e:
            logger.error(f"Unexpected error loading session: {type(e).__name__}: {e}")
            return f"Error loading session: {type(e).__name__}: {e!s}"

    def _find_session(self, session_id: str) -> sqlite3.Row | None:
        """查找会话（精确匹配后尝试模糊匹配）"""
        row = (
            self._ensure_conn()
            .execute(
                "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id = ?",
                (session_id,),
            )
            .fetchone()
        )

        if not row:
            row = (
                self._ensure_conn()
                .execute(
                    "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id LIKE ?",
                    (f"%{session_id}%",),
                )
                .fetchone()
            )
        return row

    def _format_session_message(self, msg: sqlite3.Row) -> str:
        """格式化单条会话消息"""
        role = msg["role"]
        content = msg["content"] or ""

        if msg["tool_calls_json"]:
            try:
                tc_list = json.loads(msg["tool_calls_json"])
                tc_names = [
                    tc.get("function", {}).get("name", "unknown") for tc in tc_list
                ]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            except Exception as e:
                logger.debug(f"Failed to parse tool_calls_json: {e}")

        if msg["tool_call_id"]:
            content = (msg["content"] or "")[:200]

        if len(content) > 500:
            content = content[:500] + "..."

        return f"{role}: {content}"

    def list_sessions(self, limit: int = 10) -> str:
        """列出最近会话"""
        try:
            sessions = (
                self._ensure_conn()
                .execute(
                    """
                SELECT session_id, created_at, last_updated, message_count, summary
                FROM sessions_meta
                ORDER BY created_at DESC
                LIMIT ?
            """,
                    (limit,),
                )
                .fetchall()
            )

            if not sessions:
                return "No sessions found."

            output = "Recent Sessions:\n"
            for s in sessions:
                output += f"- {s['session_id']}: {s['message_count']} msgs, {s['created_at']}\n"
                if s["summary"]:
                    summary_text = s["summary"][:100] if s["summary"] else ""
                    if summary_text:
                        output += f"  Summary: {summary_text}...\n"

            return output
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error listing sessions: {e}")
            return f"Error listing sessions (database issue): {e!s}"
        except Exception as e:
            logger.error(f"Unexpected error listing sessions: {type(e).__name__}: {e}")
            return f"Error listing sessions: {type(e).__name__}: {e!s}"

    def search_history(self, keyword: str, limit: int = 20) -> str:
        """使用 FTS5 全文搜索"""
        try:
            if not keyword.strip():
                return "Please provide a search keyword."

            fts_query = _sanitize_fts_query(keyword)
            if not fts_query:
                return f"No matches found for: {keyword}"

            query_expr = fts_query

            has_cjk = any("\u4e00" <= c <= "\u9fff" for c in fts_query)

            if has_cjk:
                tokens = fts_query.split()
                if len(tokens) > 1:
                    query_expr = " OR ".join(tokens)

            results = (
                self._ensure_conn()
                .execute(
                    """
                SELECT
                    m.session_id, m.timestamp, m.role, m.content, m.tool_call_id,
                    m.id as msg_id
                FROM session_messages m
                JOIN session_messages_fts fts ON m.id = fts.rowid
                WHERE session_messages_fts MATCH ?
                AND m.message_type = 'message'
                ORDER BY fts.rank
                LIMIT ?
            """,
                    (query_expr, limit),
                )
                .fetchall()
            )

            if not results:
                return self._fallback_search(keyword, limit)

            output = f"Found {len(results)} matches for '{keyword}':\n"
            for r in results:
                content = r["content"] or ""
                matched_preview = self._highlight_match(content, keyword)
                context = self._get_context(r["session_id"], r["msg_id"], 1)

                output += f"\n[{r['session_id']}] {r['timestamp']}\n"
                output += f"{r['role']}: {matched_preview}\n"
                output += f"Context: {context}\n"

            return output
        except sqlite3.OperationalError as e:
            logger.debug(f"FTS search failed, falling back to LIKE search: {e}")
            return self._fallback_search(keyword, limit)
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error searching history: {e}")
            return f"Error searching history (database issue): {e!s}"
        except Exception as e:
            logger.error(f"Unexpected error searching history: {type(e).__name__}: {e}")
            return f"Error searching history: {type(e).__name__}: {e!s}"

    def _fallback_search(self, keyword: str, limit: int = 20) -> str:
        """简单的字符串匹配搜索"""
        try:
            results = (
                self._ensure_conn()
                .execute(
                    """
                SELECT session_id, timestamp, role, content, id as msg_id
                FROM session_messages
                WHERE content LIKE ? AND message_type = 'message'
                LIMIT ?
            """,
                    (f"%{keyword}%", limit),
                )
                .fetchall()
            )

            if not results:
                return f"No matches found for: {keyword}"

            output = f"Found {len(results)} matches for '{keyword}':\n"
            for r in results:
                content = r["content"] or ""
                matched_preview = self._highlight_match(content, keyword)
                context = self._get_context(r["session_id"], r["msg_id"], 1)
                output += f"\n[{r['session_id']}] {r['timestamp']}\n"
                output += f"{r['role']}: {matched_preview}\n"
                output += f"Context: {context}\n"

            return output
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error in fallback search: {e}")
            return f"Error in fallback search (database issue): {e!s}"
        except Exception as e:
            logger.error(
                f"Unexpected error in fallback search: {type(e).__name__}: {e}"
            )
            return f"Error in fallback search: {type(e).__name__}: {e!s}"

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

    def _get_context(
        self, session_id: str, msg_id: int, context_size: int = 1
    ) -> list[str]:
        """获取消息的上下文"""
        try:
            context_msgs = (
                self._ensure_conn()
                .execute(
                    """
                SELECT role, content
                FROM session_messages
                WHERE session_id = ? AND message_type = 'message'
                AND id BETWEEN ? AND ?
                ORDER BY id ASC
            """,
                    (session_id, msg_id - context_size, msg_id + context_size),
                )
                .fetchall()
            )

            return [f"{m['role']}: {(m['content'] or '')[:100]}" for m in context_msgs]
        except Exception as e:
            logger.warning(f"Failed to get context messages: {type(e).__name__}: {e}")
            return []

    def _apply_filters(
        self,
        base_sql: str,
        params: list,
        session_id: str | None,
        role: str | None,
        start_time: str | None,
        end_time: str | None,
        order_by: str,
        limit: int,
    ) -> tuple[str, list]:
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
        session_id: str | None = None,
        role: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
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
                base_sql,
                params,
                session_id,
                role,
                start_time,
                end_time,
                order_by,
                limit,
            )

            rows = self._ensure_conn().execute(base_sql, params).fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Failed to get context messages: {type(e).__name__}: {e}")
            return []

    def get_session_stats(self, session_id: str) -> dict:
        """获取会话统计信息"""
        try:
            meta = (
                self._ensure_conn()
                .execute(
                    "SELECT * FROM sessions_meta WHERE session_id = ?", (session_id,)
                )
                .fetchone()
            )

            if not meta:
                return {"error": "Session not found", "error_type": "not_found"}

            fts_size = (
                self._ensure_conn()
                .execute(
                    """
                SELECT COUNT(*) as fts_count
                FROM session_messages_fts
                WHERE session_id = ?
            """,
                    (session_id,),
                )
                .fetchone()
            )

            return {
                "session_id": meta["session_id"],
                "created_at": meta["created_at"],
                "last_updated": meta["last_updated"],
                "message_count": meta["message_count"],
                "fts_indexed_count": fts_size["fts_count"],
                "has_summary": bool(meta["summary"]),
            }
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error getting session stats: {e}")
            return {"error": str(e), "error_type": "database_operational"}
        except Exception as e:
            logger.error(
                f"Unexpected error getting session stats: {type(e).__name__}: {e}"
            )
            return {"error": str(e), "error_type": type(e).__name__}

    def optimize_index(self):
        """优化 FTS5 索引"""
        try:
            self._ensure_conn().execute(
                "INSERT INTO session_messages_fts(session_messages_fts) VALUES('optimize')"
            )
            self._ensure_conn().commit()
            return "FTS5 index optimized."
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error optimizing index: {e}")
            return f"Error optimizing index (database issue): {e!s}"
        except Exception as e:
            logger.error(f"Unexpected error optimizing index: {type(e).__name__}: {e}")
            return f"Error optimizing index: {type(e).__name__}: {e!s}"

    def rebuild_index(self):
        """重建 FTS5 索引"""
        try:
            self._ensure_conn().execute(
                "INSERT INTO session_messages_fts(session_messages_fts) VALUES('rebuild')"
            )
            self._ensure_conn().commit()
            return "FTS5 index rebuilt."
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error rebuilding index: {e}")
            return f"Error rebuilding index (database issue): {e!s}"
        except Exception as e:
            logger.error(f"Unexpected error rebuilding index: {type(e).__name__}: {e}")
            return f"Error rebuilding index: {type(e).__name__}: {e!s}"

    def _generate_session_filename(self) -> str:
        """生成会话文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}.jsonl"

    def __del__(self):
        # __del__ 中不应抛出异常，静默关闭
        # 注意：在 __del__ 中调用 logger 或其他模块是不安全的
        # S110/SIM105: __del__ 中不应使用 contextlib.suppress
        # 因为 Python 解释器可能已在关闭过程中
        try:
            self.close()
        except Exception:
            pass  # 静默忽略，避免 Python 解释器关闭时的警告


# ==================== 模块级便捷函数 ====================

_db_instance: SessionDB | None = None
_db_lock = threading.Lock()  # 模块级实例锁


def _get_db() -> SessionDB:
    """获取全局 SessionDB 实例（线程安全）"""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            # 双重检查锁定模式
            if _db_instance is None:
                _db_instance = SessionDB()
    return _db_instance


def save_session_history(
    messages: list, summary: str | None = None, session_id: str | None = None
) -> str:
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
    signals: list[str] | None = None,
    session_id: str | None = None,
    context: str | None = None,
) -> str:
    """记录 Skill 执行结果"""
    return _get_db().record_skill_outcome(
        skill_name, outcome, score, signals, session_id, context
    )


def get_skill_stats(skill_name: str) -> dict:
    """获取 Skill 统计信息"""
    return _get_db().get_skill_stats(skill_name)


def list_banned_skills() -> list[BannedSkillInfo]:
    """列出被禁用的 Skill"""
    return _get_db().list_banned_skills()


def get_top_skills(limit: int = 10) -> list[dict]:
    """获取成功率最高的 Skill"""
    return _get_db().get_top_skills(limit)


def search_outcomes_by_signal(signal: str, limit: int = 20) -> list[dict]:
    """根据信号搜索执行结果"""
    return _get_db().search_outcomes_by_signal(signal, limit)
