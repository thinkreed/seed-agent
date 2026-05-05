"""
Session 事件持久化模块

处理事件的 JSONL 持久化读写。
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认存储路径获取函数（延迟导入避免循环依赖）
def _get_default_storage_path() -> Path:
    """获取默认存储路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().events_dir
    except RuntimeError:
        return Path.home() / ".seed" / "memory" / "events"


class EventPersistence:
    """事件持久化管理器"""

    def __init__(self, storage_path: Path | None = None):
        self._storage_path = storage_path or _get_default_storage_path()

    def ensure_dir_exists(self) -> None:
        """确保存储目录存在"""
        import os
        os.makedirs(self._storage_path, exist_ok=True)

    def get_event_file(self, session_id: str) -> Path:
        """获取事件文件路径"""
        return self._storage_path / f"{session_id}.jsonl"

    def persist_event(
        self,
        session_id: str,
        event: dict[str, Any],
        max_retries: int = 3,
    ) -> None:
        """持久化单个事件

        Args:
            session_id: 会话 ID
            event: 事件数据
            max_retries: 最大重试次数

        Raises:
            OSError: 重试失败后抛出异常
        """
        event_file = self.get_event_file(session_id)
        last_error: OSError | None = None

        for attempt in range(max_retries):
            try:
                with open(event_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
                return
            except OSError as e:
                last_error = e
                logger.warning(
                    f"Failed to persist event (attempt {attempt + 1}/{max_retries}): "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))

        if last_error:
            logger.error(
                f"Failed to persist event after {max_retries} retries: "
                f"{type(last_error).__name__}"
            )
            raise last_error

    def load_events(self, session_id: str) -> list[dict[str, Any]]:
        """加载会话的所有事件

        Args:
            session_id: 会话 ID

        Returns:
            事件列表
        """
        event_file = self.get_event_file(session_id)

        if not event_file.exists():
            return []

        events: list[dict[str, Any]] = []
        try:
            with open(event_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to parse event: {type(e).__name__}: {str(e)[:50]}"
                        )
                        continue

            logger.info(f"Loaded {len(events)} events for session {session_id}")
        except OSError as e:
            logger.warning(f"Failed to load events: {type(e).__name__}: {e}")

        return events