"""请求执行模块

重构版本：原大文件已拆分为多个小模块
此文件保留为向后兼容的导入入口

模块结构:
- _client_factory.py: 客户端创建 (~101 行)
- _request_handler.py: 请求执行 (~110 行)
- _streaming.py: 流式请求 (~70 行)
- _error_handler.py: 错误处理 (~93 行)
- _audit.py: 审计日志 (~99 行)

总计: 5 个模块，每个均 < 150 行
"""

from src.security.proxy._audit import (
    persist_request_audit,
    sanitize_request_context,
)
from src.security.proxy._client_factory import (
    PROVIDER_CONFIGS,
    create_temp_client,
    destroy_temp_client,
    get_supported_providers,
    register_provider,
)
from src.security.proxy._request_handler import execute_external_request
from src.security.proxy._streaming import (
    execute_streaming_request,
    finalize_streaming_request,
)

__all__ = [
    "PROVIDER_CONFIGS",
    "create_temp_client",
    "destroy_temp_client",
    "get_supported_providers",
    "register_provider",
    "execute_external_request",
    "execute_streaming_request",
    "finalize_streaming_request",
    "sanitize_request_context",
    "persist_request_audit",
]