"""记忆操作模块

用户观察、会话归档等操作
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def observe_user_interaction(
    user_modeling: Any, interaction: dict[str, Any]
) -> list[str]:
    """观察用户交互

    Args:
        user_modeling: UserModelingLayer 实例
        interaction: 交互数据

    Returns:
        观察记录列表
    """
    return user_modeling.observe_from_interaction(interaction)


def observe_preference_direct(
    user_modeling: Any,
    key: str,
    value: str,
    context: str | None = None,
    confidence: float = 0.8,
) -> str:
    """直接观察偏好

    Args:
        user_modeling: UserModelingLayer 实例
        key: 偏好键
        value: 偏好值
        context: 上下文
        confidence: 置信度

    Returns:
        观察记录状态
    """
    return user_modeling.observe(
        evidence_type="preference",
        data={"key": key, "value": value},
        context=context,
        confidence=confidence,
    )


async def update_user_model_dialectical(user_modeling: Any) -> dict[str, Any]:
    """触发用户模型辩证式更新

    Args:
        user_modeling: UserModelingLayer 实例

    Returns:
        更新报告
    """
    return await user_modeling.dialectical_update()


def get_user_preference_with_context(
    user_modeling: Any, key: str, context: str | None = None
) -> dict[str, Any]:
    """获取用户偏好

    Args:
        user_modeling: UserModelingLayer 实例
        key: 偏好键
        context: 当前上下文

    Returns:
        基于上下文的偏好值
    """
    return user_modeling.get_user_preference(key, context)


async def archive_session_to_l5(
    archive: Any,
    session_id: str,
    events: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> str:
    """归档会话到 L5

    Args:
        archive: LongTermArchiveLayer 实例
        session_id: 会话 ID
        events: 事件列表
        metadata: 可选元数据

    Returns:
        archive_id
    """
    return await archive.archive_session(session_id, events, metadata)


async def archive_from_event_stream(
    archive: Any,
    event_stream: Any,
    metadata: dict[str, Any] | None = None,
) -> str:
    """从事件流归档

    Args:
        archive: LongTermArchiveLayer 实例
        event_stream: SessionEventStream 实例
        metadata: 可选元数据

    Returns:
        archive_id
    """
    return await archive.archive_from_event_stream(event_stream, metadata)


def search_l5_archives(
    archive: Any, keyword: str, limit: int = 20
) -> list[dict[str, Any]]:
    """搜索归档

    Args:
        archive: LongTermArchiveLayer 实例
        keyword: 搜索关键词
        limit: 结果限制

    Returns:
        归档列表
    """
    return archive.search_with_context(keyword, limit)


def get_l5_archive_by_id(archive: Any, archive_id: str) -> dict[str, Any] | None:
    """获取归档详情

    Args:
        archive: LongTermArchiveLayer 实例
        archive_id: 归档 ID

    Returns:
        归档详情字典
    """
    return archive.get_archive(archive_id)


def cleanup_old_archives(archive: Any, max_age_days: int = 90) -> int:
    """清理旧归档

    Args:
        archive: LongTermArchiveLayer 实例
        max_age_days: 最大保留天数

    Returns:
        清理的归档数量
    """
    return archive.cleanup_old_archives(max_age_days)