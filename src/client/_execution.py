"""
执行层模块

提供:
- chat_completion_single: 单 Provider 调用
- try_provider_with_retry: 尝试单个 provider 调用（带重试）
- try_fallback_providers: 尝试所有 fallback providers
- chat_completion_with_fallback_internal: 带降级的非流式聊天补全
- get_fallback_model_id: 获取 fallback provider 的等效模型
- iterate_fallback_models: 生成 fallback provider 和 model_id 列表

实现已拆分至 execution_core/ 子模块。
"""

from src.client.execution_core import (
    chat_completion_single,
    chat_completion_with_fallback_internal,
    get_fallback_model_id,
    iterate_fallback_models,
    try_fallback_providers,
    try_provider_with_retry,
)

__all__ = [
    "chat_completion_single",
    "chat_completion_with_fallback_internal",
    "get_fallback_model_id",
    "iterate_fallback_models",
    "try_fallback_providers",
    "try_provider_with_retry",
]