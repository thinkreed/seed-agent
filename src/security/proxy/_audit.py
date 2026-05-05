"""
审计日志模块

内部模块，负责请求审计日志的记录和统计。

核心功能:
- 请求日志记录
- 统计信息计算
- 日志持久化
"""

from typing import Any

from src.security.proxy._types import RequestAuditLog


class AuditLogManager:
    """审计日志管理器

    管理请求审计日志的记录、存储和统计。

    Attributes:
        _request_logs: 请求日志列表
        _max_request_logs: 最大日志条数
    """

    def __init__(self, max_request_logs: int = 10000):
        """初始化审计日志管理器

        Args:
            max_request_logs: 最大日志条数
        """
        self._request_logs: list[RequestAuditLog] = []
        self._max_request_logs = max_request_logs

    def add_log(self, log_entry: RequestAuditLog) -> None:
        """添加请求日志

        Args:
            log_entry: 审计日志条目
        """
        self._request_logs.append(log_entry)

        # 限制日志大小
        if len(self._request_logs) > self._max_request_logs:
            self._request_logs = self._request_logs[-self._max_request_logs :]

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取请求审计日志

        Args:
            limit: 返回条数限制

        Returns:
            审计日志列表
        """
        logs = self._request_logs[-limit:]
        return [
            {
                "timestamp": log.timestamp,
                "provider": log.provider,
                "credential_type": log.credential_type,
                "requester_id": log.requester_id,
                "status": log.status,
                "duration_ms": log.duration_ms,
                "request_context": log.request_context,
                "error": log.error,
            }
            for log in logs
        ]

    def get_stats(self, active_clients_count: int = 0) -> dict[str, Any]:
        """获取请求统计信息（单次遍历优化）

        Args:
            active_clients_count: 活跃客户端数量

        Returns:
            统计信息字典
        """
        total_requests = len(self._request_logs)
        successful = 0
        failed = 0
        timeouts = 0
        total_duration = 0.0
        by_provider: dict[str, dict[str, int]] = {}

        # 单次遍历计算所有统计值
        for log in self._request_logs:
            # 状态统计
            if log.status == "success":
                successful += 1
            elif log.status == "failed":
                failed += 1
            elif log.status == "timeout":
                timeouts += 1

            # 耗时累计
            total_duration += log.duration_ms

            # 按 Provider 统计
            if log.provider not in by_provider:
                by_provider[log.provider] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "timeout": 0,
                }
            by_provider[log.provider]["total"] += 1
            by_provider[log.provider][log.status] += 1

        avg_duration = total_duration / total_requests if total_requests else 0.0

        return {
            "total_requests": total_requests,
            "successful": successful,
            "failed": failed,
            "timeouts": timeouts,
            "success_rate": (successful / total_requests * 100)
            if total_requests
            else 100.0,
            "average_duration_ms": avg_duration,
            "by_provider": by_provider,
            "active_clients": active_clients_count,
        }

    def clear(self) -> None:
        """清空请求审计日志"""
        self._request_logs.clear()

    @property
    def count(self) -> int:
        """获取日志条数"""
        return len(self._request_logs)