"""
L4 用户建模层 - 黑格尔辩证式进化

核心理念:
- 不是一次判断就定终身，允许用户改变、允许情况复杂
- 通过不断观察、思考、调整，越来越懂真实的用户
- 升级而非覆盖：保留例外情况和复杂偏好

特性:
- 观察 → 矛盾检测 → 内部推理 → 升级模型
- 允许例外和复杂情况
- 辩证式历史记录（进化可追溯）
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)

# 数据库路径
USER_MODELING_DB_PATH = Path.home() / ".seed" / "memory" / "user_modeling.db"


class UserModelingLayer:
    """L4 用户建模 - 黑格尔辩证式进化

    核心功能:
    1. observe(): 观察用户行为和偏好
    2. dialectical_update(): 辩证式更新模型
    3. get_user_preference(): 获取基于上下文的偏好
    4. get_user_profile_summary(): 获取用户画像摘要

    数据库 Schema:
    - user_profiles: 用户画像主表
    - user_observations: 观察记录表
    - dialectical_history: 辩证进化历史表
    """

    _instance: "UserModelingLayer | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> "UserModelingLayer":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self, db_path: str | Path | None = None, llm_gateway: "LLMGateway | None" = None
    ):
        with UserModelingLayer._lock:
            if UserModelingLayer._initialized:
                return
            UserModelingLayer._initialized = True

        self.db_path = str(db_path or USER_MODELING_DB_PATH)
        self._llm_gateway = llm_gateway
        self.conn: sqlite3.Connection | None = None
        self._init_db()

    def set_llm_gateway(self, gateway: "LLMGateway") -> None:
        """设置 LLM Gateway（用于内部推理）"""
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
                UserModelingLayer._instance = None
                UserModelingLayer._initialized = False

    def _ensure_conn(self) -> sqlite3.Connection:
        """确保数据库连接可用"""
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn

    def _create_schema(self) -> None:
        """创建数据库 Schema"""
        cursor = self._ensure_conn().cursor()

        # 用户画像主表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                profile_id TEXT PRIMARY KEY,
                preference_key TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.8,
                last_updated TEXT NOT NULL,
                metadata TEXT,
                UNIQUE(profile_id, preference_key)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_profiles_key ON user_profiles(preference_key)"
        )

        # 观察记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_type TEXT NOT NULL,
                observation_data TEXT NOT NULL,
                context TEXT,
                confidence REAL DEFAULT 0.8,
                timestamp TEXT NOT NULL,
                processed INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_type ON user_observations(observation_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_time ON user_observations(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_unprocessed ON user_observations(processed)"
        )

        # 辩证进化历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dialectical_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conflict TEXT NOT NULL,
                resolution TEXT NOT NULL,
                update_record TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                reasoning_log TEXT
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dialectical_time ON dialectical_history(timestamp)"
        )

        self._ensure_conn().commit()

    # === 观察 ===

    def observe(
        self,
        evidence_type: str,
        data: dict[str, Any],
        context: str | None = None,
        confidence: float = 0.8,
    ) -> str:
        """观察新证据

        Args:
            evidence_type: "preference" | "behavior" | "feedback" | "context"
            data: 具体观察内容，格式 {"key": "...", "value": "..."}
            context: 观察上下文
            confidence: 置信度 (0.0-1.0)

        Returns:
            观察记录状态
        """
        if evidence_type not in ("preference", "behavior", "feedback", "context"):
            return f"Invalid evidence type: {evidence_type}"

        if not (0.0 <= confidence <= 1.0):
            return f"Invalid confidence: {confidence} (must be 0.0-1.0)"

        timestamp = datetime.now(tz=timezone.utc).isoformat()
        data_json = json.dumps(data, ensure_ascii=False)

        try:
            self._ensure_conn().execute(
                """
                INSERT INTO user_observations
                    (observation_type, observation_data, context, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (evidence_type, data_json, context or "", confidence, timestamp),
            )
            self._ensure_conn().commit()

            return (
                f"Observation recorded: {evidence_type} -> {data.get('key', 'unknown')}"
            )
        except sqlite3.Error as e:
            return f"Error recording observation: {type(e).__name__}: {e}"

    def observe_from_interaction(self, interaction: dict[str, Any]) -> list[str]:
        """从用户交互中提取观察

        Args:
            interaction: {
                "user_message": str,
                "agent_response": str,
                "tool_calls": list,
                "feedback": str | None
            }

        Returns:
            观察记录列表
        """
        results = []

        user_message = interaction.get("user_message", "")
        feedback = interaction.get("feedback")

        # 提取偏好线索
        preferences = self._extract_preferences_from_message(user_message)
        for pref in preferences:
            result = self.observe(
                evidence_type="preference",
                data=pref,
                context=user_message[:200],
                confidence=0.7,
            )
            results.append(result)

        # 提取行为模式（从工具调用）
        tool_calls = interaction.get("tool_calls", [])
        if tool_calls:
            behaviors = self._extract_behaviors_from_tools(tool_calls)
            for beh in behaviors:
                result = self.observe(
                    evidence_type="behavior",
                    data=beh,
                    context=json.dumps(tool_calls[:3], ensure_ascii=False),
                    confidence=0.6,
                )
                results.append(result)

        # 显式反馈（高置信度）
        if feedback:
            result = self.observe(
                evidence_type="feedback",
                data={"key": "explicit_feedback", "value": feedback},
                context=user_message[:200],
                confidence=0.9,
            )
            results.append(result)

        return results

    def _extract_preferences_from_message(self, message: str) -> list[dict[str, Any]]:
        """从用户消息中提取偏好线索

        简单规则匹配：
        - "我喜欢..." -> preference
        - "我不喜欢..." -> preference (negative)
        - "用xxx格式" -> preference
        """
        preferences = []

        # 正向偏好
        if "我喜欢" in message or "prefer" in message.lower():
            preferences.append(
                {"key": "general_style", "value": "user_likes", "raw": message[:100]}
            )

        # 格式偏好
        if "格式" in message or "format" in message.lower():
            preferences.append(
                {
                    "key": "output_format",
                    "value": "specified_format",
                    "raw": message[:100],
                }
            )

        # 语言偏好
        if "用中文" in message or "用英文" in message:
            lang = "中文" if "中文" in message else "英文"
            preferences.append({"key": "language", "value": lang, "raw": message[:100]})

        return preferences

    def _extract_behaviors_from_tools(
        self, tool_calls: list[dict]
    ) -> list[dict[str, Any]]:
        """从工具调用中提取行为模式"""
        behaviors = []

        for tc in tool_calls[:5]:
            tool_name = tc.get("function", {}).get("name", "unknown")
            behaviors.append(
                {"key": "tool_usage", "value": tool_name, "frequency": "observed"}
            )

        return behaviors

    # === 辩证式更新 ===

    async def dialectical_update(self) -> dict[str, Any]:
        """辩证式更新

        流程:
        1. 检测新证据与旧模型矛盾
        2. 内部推理讨论（使用 LLM）
        3. 升级用户模型（不直接覆盖）

        Returns:
            更新报告
        """
        # 1. 获取未处理的观察
        unprocessed = self._get_unprocessed_observations()

        if not unprocessed:
            return {"status": "no_new_observations", "conflicts": [], "updates": []}

        # 2. 检测矛盾
        conflicts = await self._detect_conflicts(unprocessed)

        if not conflicts:
            # 无矛盾，直接强化现有模型
            await self._reinforce_model(unprocessed)
            self._mark_observations_processed(unprocessed)
            return {"status": "reinforced", "conflicts": [], "updates": unprocessed}

        # 3. 内部推理讨论
        resolution = await self._reason_about_conflicts(conflicts)

        # 4. 升级模型（不直接覆盖）
        updates = self._upgrade_model(resolution)

        # 5. 标记观察已处理
        self._mark_observations_processed(unprocessed)

        # 6. 记录进化历史
        self._record_dialectical_history(conflicts, resolution, updates)

        return {
            "status": "upgraded",
            "conflicts": conflicts,
            "resolution": resolution,
            "updates": updates,
        }

    def _get_unprocessed_observations(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取未处理的观察记录（按时间升序，先添加的先处理）"""
        rows = (
            self._ensure_conn()
            .execute(
                """
            SELECT id, observation_type, observation_data, context, confidence, timestamp
            FROM user_observations
            WHERE processed = 0
            ORDER BY timestamp ASC
            LIMIT ?
        """,
                (limit,),
            )
            .fetchall()
        )

        observations = []
        for row in rows:
            data = json.loads(row["observation_data"])
            observations.append(
                {
                    "id": row["id"],
                    "type": row["observation_type"],
                    "data": data,
                    "context": row["context"],
                    "confidence": row["confidence"],
                    "timestamp": row["timestamp"],
                }
            )

        return observations

    def _mark_observations_processed(self, observations: list[dict[str, Any]]) -> None:
        """标记观察已处理"""
        ids = [str(o["id"]) for o in observations]
        if ids:
            # 使用参数化查询防止 SQL 注入，placeholders 只是占位符
            placeholders = ",".join("?" * len(ids))
            self._ensure_conn().execute(
                f"UPDATE user_observations SET processed = 1 WHERE id IN ({placeholders})",
                ids,
            )
            self._ensure_conn().commit()

    async def _detect_conflicts(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """检测新证据与旧模型的矛盾

        Returns:
            冲突列表: [{
                "old_belief": {...},
                "new_evidence": {...},
                "confidence_old": 0.85,
                "confidence_new": 0.9,
                "context": "周三下午"
            }]
        """
        conflicts = []

        # 收集所有需要查询的偏好键（批量加载避免 N+1）
        pref_keys = set()
        for obs in observations:
            if obs["type"] == "preference":
                key = obs["data"].get("key")
                if key:
                    pref_keys.add(key)

        # 批量获取所有偏好
        existing_prefs = self._get_preferences_batch(pref_keys) if pref_keys else {}

        for obs in observations:
            if obs["type"] != "preference":
                continue

            pref_key = obs["data"].get("key")
            pref_value = obs["data"].get("value")

            if not pref_key or not pref_value:
                continue

            # 从批量结果中获取现有偏好
            existing = existing_prefs.get(pref_key)

            if existing and self._is_conflicting(existing, pref_value, obs["context"]):
                conflicts.append(
                    {
                        "preference_key": pref_key,
                        "old_belief": existing,
                        "new_evidence": pref_value,
                        "confidence_old": existing.get("confidence", 0.8),
                        "confidence_new": obs["confidence"],
                        "context": obs["context"],
                        "observation_id": obs["id"],
                    }
                )

        return conflicts

    def _get_preference_from_db(self, key: str) -> dict[str, Any] | None:
        """从数据库获取偏好"""
        row = (
            self._ensure_conn()
            .execute(
                """
            SELECT preference_value, confidence, last_updated, metadata
            FROM user_profiles
            WHERE preference_key = ?
            ORDER BY last_updated DESC
            LIMIT 1
        """,
                (key,),
            )
            .fetchone()
        )

        if row:
            # preference_value 存储的是完整的 JSON 字符串
            pref_data = json.loads(row["preference_value"])
            return {
                "value": pref_data.get("usual", pref_data.get("value")),
                "confidence": pref_data.get("confidence", row["confidence"]),
                "last_updated": pref_data.get("last_updated", row["last_updated"]),
                "exceptions": pref_data.get("exceptions", {}),
                "usual": pref_data.get("usual", pref_data.get("value")),
            }

        return None

    def _get_preferences_batch(self, keys: set[str]) -> dict[str, dict[str, Any]]:
        """批量从数据库获取偏好（避免 N+1 查询）

        Args:
            keys: 偏好键集合

        Returns:
            dict: {key: preference_data}
        """
        if not keys:
            return {}

        # 使用单个查询获取所有偏好
        placeholders = ",".join("?" * len(keys))
        rows = (
            self._ensure_conn()
            .execute(
                f"""
            SELECT preference_key, preference_value, confidence, last_updated, metadata
            FROM user_profiles
            WHERE preference_key IN ({placeholders})
            ORDER BY preference_key, last_updated DESC
        """,
                list(keys),
            )
            .fetchall()
        )

        # 解析结果，每个 key 取最新的
        result: dict[str, dict[str, Any]] = {}
        seen_keys: set[str] = set()

        for row in rows:
            key = row["preference_key"]
            if key in seen_keys:
                continue  # 已有更新的记录
            seen_keys.add(key)

            pref_data = json.loads(row["preference_value"])
            result[key] = {
                "value": pref_data.get("usual", pref_data.get("value")),
                "confidence": pref_data.get("confidence", row["confidence"]),
                "last_updated": pref_data.get("last_updated", row["last_updated"]),
                "exceptions": pref_data.get("exceptions", {}),
                "usual": pref_data.get("usual", pref_data.get("value")),
            }

        return result

    def _is_conflicting(
        self, existing: dict[str, Any], new_value: str, context: str | None
    ) -> bool:
        """检查是否矛盾

        规则:
        1. 如果新值与旧值不同，且上下文不匹配例外情况，则矛盾
        2. 相同值不矛盾
        """
        usual = existing.get("usual", existing.get("value"))

        if new_value == usual:
            return False

        # 检查例外情况
        exceptions = existing.get("exceptions", {})
        if context:
            for exc_key, exc_value in exceptions.items():
                if (
                    exc_key in context or context in exc_key
                ) and new_value == exc_value.get("value"):
                    return False  # 匹配例外，不矛盾

        # 新值不同，无匹配例外 -> 矛盾
        return True

    async def _reason_about_conflicts(
        self, conflicts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """内部推理讨论

        使用 LLM 分析矛盾，得出升级方案
        """
        if not self._llm_gateway:
            # 无 LLM Gateway，使用简单规则
            return self._simple_resolution(conflicts)

        # 构建 prompt
        prompt = self._build_reasoning_prompt(conflicts)

        try:
            # 调用 LLM
            result = await self._llm_gateway.chat_completion(
                model_id="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                priority=2,  # HIGH
            )

            response_text = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return self._parse_resolution_response(response_text, conflicts)
        except Exception as e:
            logger.warning(f"LLM reasoning failed: {type(e).__name__}: {e}")
            return self._simple_resolution(conflicts)

    def _build_reasoning_prompt(self, conflicts: list[dict[str, Any]]) -> str:
        """构建推理 prompt"""
        conflict_descs = []
        for c in conflicts:
            conflict_descs.append(
                f"- 原有认知: 用户偏好 '{c['preference_key']}' = '{c['old_belief'].get('usual', c['old_belief'].get('value'))}' "
                f"(置信度 {c['confidence_old']:.2f})"
            )
            conflict_descs.append(
                f"- 新证据: 观察到 '{c['new_evidence']}' "
                f"(置信度 {c['confidence_new']:.2f}, 上下文: {c['context'] or '无'})"
            )

        return f"""作为用户建模专家，分析以下矛盾并给出升级方案。

矛盾列表:
{chr(10).join(conflict_descs)}

请分析:
1. 这是真正的偏好改变，还是特定上下文下的例外情况？
2. 如何升级用户模型（不是简单覆盖，而是保留例外）？

请以 JSON 格式返回:
{
            "resolutions": [
    {
                "preference_key": "...",
      "resolution_type": "exception" | "upgrade",
      "value": "...",
      "when": "例外条件（如果 resolution_type=exception）",
      "reason": "推理理由",
      "confidence": 0.XX
    }
  ]
}
"""

    def _parse_resolution_response(
        self, response: str, conflicts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """解析 LLM 返回的决议"""
        try:
            # 提取 JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM resolution response")

        return self._simple_resolution(conflicts)

    def _simple_resolution(self, conflicts: list[dict[str, Any]]) -> dict[str, Any]:
        """简单规则决议（无 LLM 时）"""
        resolutions = []

        for c in conflicts:
            context = c.get("context", "")

            if context:
                # 有上下文，视为例外
                resolutions.append(
                    {
                        "preference_key": c["preference_key"],
                        "resolution_type": "exception",
                        "value": c["new_evidence"],
                        "when": context[:100],
                        "reason": "有明确上下文，视为例外情况",
                        "confidence": min(c["confidence_old"], c["confidence_new"]),
                    }
                )
            else:
                # 无上下文，视为升级
                resolutions.append(
                    {
                        "preference_key": c["preference_key"],
                        "resolution_type": "upgrade",
                        "value": c["new_evidence"],
                        "when": "",
                        "reason": "无上下文约束，视为偏好升级",
                        "confidence": c["confidence_new"],
                    }
                )

        return {"resolutions": resolutions}

    async def _reinforce_model(self, observations: list[dict[str, Any]]) -> None:
        """强化现有模型（无矛盾时）

        处理规则：
        - 新偏好（无 existing）：直接设置
        - 相同值（与 existing.usual 相同）：强化置信度
        - 不同值但有上下文：添加例外
        - 不同值无上下文：视为偏好升级（较高置信度时）
        """
        for obs in observations:
            if obs["type"] != "preference":
                continue

            pref_key = obs["data"].get("key")
            pref_value = obs["data"].get("value")

            if not pref_key or not pref_value:
                continue

            existing = self._get_preference_from_db(pref_key)

            if existing:
                usual = existing.get("usual", existing.get("value"))

                if pref_value == usual:
                    # 相同值：强化置信度
                    new_confidence = min(1.0, existing["confidence"] + 0.05)
                    self._update_preference_confidence(pref_key, new_confidence)
                elif obs.get("context"):
                    # 不同值但有上下文：添加例外
                    self._add_exception(
                        pref_key, pref_value, obs["context"], obs["confidence"]
                    )
                # 不同值无上下文：偏好升级（仅当置信度更高时）
                elif obs["confidence"] > existing["confidence"]:
                    self._upgrade_preference(pref_key, pref_value, obs["confidence"])
            else:
                # 新偏好，直接设置
                self._set_preference(pref_key, pref_value, obs["confidence"])

    def _upgrade_model(self, resolution: dict[str, Any]) -> list[dict[str, Any]]:
        """升级模型而非简单覆盖

        示例:
        - 不是: preference = "拿铁"
        - 而是: preference = {"usual": "美式", "exceptions": {"周三下午": "拿铁"}}
        """
        updates = []

        for res in resolution.get("resolutions", []):
            pref_key = res.get("preference_key")
            if not pref_key:
                continue

            existing = self._get_preference_from_db(pref_key)

            if res.get("resolution_type") == "exception":
                # 添加例外
                upgraded = self._apply_exception_upgrade(existing, res)
            else:
                # 升级常规偏好
                upgraded = self._apply_value_upgrade(existing, res)

            # 保存到数据库
            self._save_preference(pref_key, upgraded)

            updates.append(
                {
                    "preference_key": pref_key,
                    "before": existing,
                    "after": upgraded,
                    "reason": res.get("reason", ""),
                }
            )

        return updates

    def _apply_exception_upgrade(
        self, existing: dict[str, Any] | None, resolution: dict[str, Any]
    ) -> dict[str, Any]:
        """添加例外升级"""
        if not existing:
            # 无现有偏好，直接设置
            return {
                "usual": resolution["value"],
                "exceptions": {},
                "confidence": resolution["confidence"],
                "last_updated": datetime.now(tz=timezone.utc).isoformat(),
            }

        # 添加例外
        exceptions = existing.get("exceptions", {})
        when_key = resolution.get("when", "general")[:50]
        exceptions[when_key] = {
            "value": resolution["value"],
            "when": resolution.get("when", ""),
            "confidence": resolution["confidence"],
        }

        return {
            "usual": existing.get("usual", existing.get("value")),
            "exceptions": exceptions,
            "confidence": min(existing["confidence"], resolution["confidence"]),
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }

    def _apply_value_upgrade(
        self, existing: dict[str, Any] | None, resolution: dict[str, Any]
    ) -> dict[str, Any]:
        """升级常规偏好"""
        if not existing:
            return {
                "usual": resolution["value"],
                "exceptions": {},
                "confidence": resolution["confidence"],
                "last_updated": datetime.now(tz=timezone.utc).isoformat(),
            }

        # 升级常规值，保留旧值作为历史例外
        exceptions = existing.get("exceptions", {})
        old_usual = existing.get("usual", existing.get("value"))
        exceptions["previously"] = {
            "value": old_usual,
            "when": "之前的偏好",
            "confidence": existing["confidence"],
        }

        return {
            "usual": resolution["value"],
            "exceptions": exceptions,
            "confidence": resolution["confidence"],
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }

    def _save_preference(self, key: str, pref_data: dict[str, Any]) -> None:
        """保存偏好到数据库"""
        profile_id = f"user_{key}"
        value_json = json.dumps(pref_data, ensure_ascii=False)
        metadata = json.dumps(
            {"exceptions": pref_data.get("exceptions", {})}, ensure_ascii=False
        )

        self._ensure_conn().execute(
            """
            INSERT OR REPLACE INTO user_profiles
                (profile_id, preference_key, preference_value, confidence, last_updated, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                profile_id,
                key,
                value_json,
                pref_data["confidence"],
                pref_data["last_updated"],
                metadata,
            ),
        )
        self._ensure_conn().commit()

    def _set_preference(self, key: str, value: str, confidence: float) -> None:
        """设置新偏好"""
        pref_data = {
            "usual": value,
            "exceptions": {},
            "confidence": confidence,
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save_preference(key, pref_data)

    def _update_preference_confidence(self, key: str, new_confidence: float) -> None:
        """更新偏好置信度"""
        self._ensure_conn().execute(
            """
            UPDATE user_profiles
            SET confidence = ?, last_updated = ?
            WHERE preference_key = ?
        """,
            (new_confidence, datetime.now(tz=timezone.utc).isoformat(), key),
        )
        self._ensure_conn().commit()

    def _add_exception(
        self, key: str, value: str, context: str, confidence: float
    ) -> None:
        """添加例外情况"""
        existing = self._get_preference_from_db(key)
        if not existing:
            return

        exceptions = existing.get("exceptions", {})
        when_key = context[:50]
        exceptions[when_key] = {
            "value": value,
            "when": context,
            "confidence": confidence,
        }

        pref_data = {
            "usual": existing.get("usual", existing.get("value")),
            "exceptions": exceptions,
            "confidence": existing["confidence"],
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save_preference(key, pref_data)

    def _upgrade_preference(
        self, key: str, new_value: str, new_confidence: float
    ) -> None:
        """升级偏好值（保留旧值作为历史例外）"""
        existing = self._get_preference_from_db(key)
        if not existing:
            return

        exceptions = existing.get("exceptions", {})
        old_usual = existing.get("usual", existing.get("value"))
        exceptions["previously"] = {
            "value": old_usual,
            "when": "升级前的偏好值",
            "confidence": existing["confidence"],
        }

        pref_data = {
            "usual": new_value,
            "exceptions": exceptions,
            "confidence": new_confidence,
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save_preference(key, pref_data)

    def _record_dialectical_history(
        self,
        conflicts: list[dict[str, Any]],
        resolution: dict[str, Any],
        updates: list[dict[str, Any]],
    ) -> None:
        """记录辩证进化历史"""
        timestamp = datetime.now(tz=timezone.utc).isoformat()

        conflict_json = json.dumps(conflicts, ensure_ascii=False)
        resolution_json = json.dumps(resolution, ensure_ascii=False)
        update_json = json.dumps(updates, ensure_ascii=False)

        self._ensure_conn().execute(
            """
            INSERT INTO dialectical_history (conflict, resolution, update_record, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (conflict_json, resolution_json, update_json, timestamp),
        )
        self._ensure_conn().commit()

    # === 用户画像查询 ===

    def get_user_preference(
        self, key: str, context: str | None = None
    ) -> dict[str, Any]:
        """获取用户偏好

        Args:
            key: 偏好键 (如 "coffee", "work_style")
            context: 当前上下文 (用于检查例外)

        Returns:
            基于上下文的偏好值
        """
        existing = self._get_preference_from_db(key)

        if not existing:
            return {"value": None, "reason": "无此偏好记录", "confidence": 0.0}

        # 检查是否有例外匹配当前上下文
        exceptions = existing.get("exceptions", {})
        if context and exceptions:
            for exc_key, exc_value in exceptions.items():
                if exc_key in context or context in exc_key:
                    return {
                        "value": exc_value.get("value"),
                        "reason": f"例外情况: {exc_value.get('when', exc_key)}",
                        "confidence": exc_value.get("confidence", 0.7),
                    }

        return {
            "value": existing.get("usual", existing.get("value")),
            "reason": "常规偏好",
            "confidence": existing.get("confidence", 0.5),
        }

    def get_user_profile_summary(self) -> str:
        """获取用户画像摘要"""
        rows = (
            self._ensure_conn()
            .execute("""
            SELECT preference_key, preference_value, confidence
            FROM user_profiles
            ORDER BY confidence DESC, last_updated DESC
        """)
            .fetchall()
        )

        if not rows:
            return "无用户画像数据"

        lines = ["用户画像摘要:"]
        for row in rows:
            pref_data = json.loads(row["preference_value"])
            usual = pref_data.get("usual", "未知")
            exceptions = pref_data.get("exceptions", {})

            if exceptions:
                exception_strs = [
                    f"{k}: {v.get('value', '未知')}"
                    for k, v in exceptions.items()
                    if k != "previously"
                ]
                if exception_strs:
                    lines.append(
                        f"- {row['preference_key']}: 平时 {usual}, "
                        f"例外情况 {', '.join(exception_strs[:3])}"
                    )
                else:
                    lines.append(f"- {row['preference_key']}: {usual}")
            else:
                lines.append(f"- {row['preference_key']}: {usual}")

        return chr(10).join(lines)

    def get_dialectical_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取辩证进化历史"""
        rows = (
            self._ensure_conn()
            .execute(
                """
            SELECT id, conflict, resolution, update_record, timestamp, reasoning_log
            FROM dialectical_history
            ORDER BY timestamp DESC
            LIMIT ?
        """,
                (limit,),
            )
            .fetchall()
        )

        history = []
        for row in rows:
            history.append(
                {
                    "id": row["id"],
                    "conflict": json.loads(row["conflict"]),
                    "resolution": json.loads(row["resolution"]),
                    "update": json.loads(row["update_record"]),
                    "timestamp": row["timestamp"],
                    "reasoning_log": row["reasoning_log"],
                }
            )

        return history

    def get_all_preferences(self) -> dict[str, dict[str, Any]]:
        """获取所有偏好"""
        rows = (
            self._ensure_conn()
            .execute("""
            SELECT preference_key, preference_value, confidence
            FROM user_profiles
        """)
            .fetchall()
        )

        preferences = {}
        for row in rows:
            preferences[row["preference_key"]] = json.loads(row["preference_value"])

        return preferences

    def clear_preference(self, key: str) -> str:
        """清除特定偏好"""
        self._ensure_conn().execute(
            "DELETE FROM user_profiles WHERE preference_key = ?", (key,)
        )
        self._ensure_conn().commit()
        return f"Preference cleared: {key}"

    def clear_all_observations(self) -> str:
        """清除所有观察记录"""
        self._ensure_conn().execute("DELETE FROM user_observations")
        self._ensure_conn().commit()
        return "All observations cleared"
