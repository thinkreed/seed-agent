"""
代理类型定义 - RequestAuditLog

内部模块，定义凭证代理相关的数据类型。
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class RequestAuditLog:
    """请求审计日志

    记录所有通过 CredentialProxy 执行的外部请求详情，
    用于安全审计和问题追溯。

    Attributes:
        timestamp: 请求时间戳（Unix 时间）
        provider: 提供商名称（如 "openai", "anthropic"）
        credential_type: 凭证类型（如 "api_key"）
        requester_id: 请求者标识符
        status: 请求状态（success, failed, timeout）
        duration_ms: 请求耗时（毫秒）
        request_context: 请求上下文（已过滤敏感信息）
        error: 错误信息（失败时）
    """

    timestamp: float
    provider: str
    credential_type: str
    requester_id: str | None
    status: str  # success, failed, timeout
    duration_ms: float
    request_context: dict[str, Any]
    error: str | None = None