"""MessageBus 相关类型

包含 PendingRequest 等消息总线所需类型。
"""

import asyncio
from dataclasses import dataclass, field


@dataclass
class PendingRequest:
    """等待中的请求 (用于 MessageBus)

    Attributes:
        correlation_id: 请求关联 ID
        request_type: 请求类型
        future: asyncio.Future 用于等待响应
        created_at: 创建时间
        timeout_ms: 超时时间（毫秒）
    """

    correlation_id: str
    request_type: str
    future: asyncio.Future
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    timeout_ms: int = 60000


__all__ = ["PendingRequest"]