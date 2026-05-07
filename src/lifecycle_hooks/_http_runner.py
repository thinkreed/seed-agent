"""HTTP 钩子执行器入口 (Wiki 知识落地 - Qwen-Code)

模块拆分：
- _http_runner_types.py: 类型定义
- _http_runner_async.py: 异步执行器
- _http_runner_sync.py: 同步执行器

基于 Qwen-Code HTTP Hooks 设计：
- 在生命周期节点发送 HTTP 请求
- 支持多种请求方法 (GET/POST/PUT/DELETE)
- 支持自定义 headers 和 body
- 超时控制和错误处理

使用场景：
- 触发外部 Webhook
- 调用监控系统 API
- 发送通知到 Slack/Discord
"""

# 导入所有模块
from ._http_runner_async import HttpHookRunner
from ._http_runner_sync import execute_http_hook_sync
from ._http_runner_types import HttpHookConfig, HttpHookResult

__all__ = [
    "HttpHookConfig",
    "HttpHookResult",
    "HttpHookRunner",
    "execute_http_hook_sync",
]