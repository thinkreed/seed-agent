"""
凭证代理子模块

基于 Harness Engineering "凭证永不进沙盒" 设计理念。

公共接口:
- CredentialProxy: 凭证代理主类（从父模块导入）
- TemporaryClient: 临时客户端
- RequestAuditLog: 请求审计日志

内部模块（私有）:
- _types: 数据类型定义
- _temp_client: 临时客户端管理
- _execution: 请求执行逻辑
- _audit: 审计日志管理
"""

from src.security.proxy._audit import AuditLogManager
from src.security.proxy._execution import (
    PROVIDER_CONFIGS,
    create_temp_client,
    destroy_temp_client,
    execute_external_request,
    execute_streaming_request,
    finalize_streaming_request,
    get_supported_providers,
    persist_request_audit,
    register_provider,
    sanitize_request_context,
)
from src.security.proxy._temp_client import TemporaryClient
from src.security.proxy._types import RequestAuditLog

__all__ = [
    # Provider 配置
    "PROVIDER_CONFIGS",
    # 审计管理器
    "AuditLogManager",
    "RequestAuditLog",
    # 公共类型
    "TemporaryClient",
    # 执行函数（供 CredentialProxy 内部使用）
    "create_temp_client",
    "destroy_temp_client",
    "execute_external_request",
    "execute_streaming_request",
    "finalize_streaming_request",
    # Provider 管理
    "get_supported_providers",
    "persist_request_audit",
    "register_provider",
    "sanitize_request_context",
]