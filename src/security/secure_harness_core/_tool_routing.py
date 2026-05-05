"""
工具路由模块

提供带凭证安全检查的工具路由功能：
- _route_tool_calls: 路由工具调用到 Sandbox

核心特性：
- CredentialIsolatedSandbox 集成
- 自动隔离执行
- 结果格式转换
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolRoutingMixin:
    """工具路由功能 Mixin

    提供 _route_tool_calls 方法。
    需要与 SecureHarness 配合使用，依赖 sandbox 等属性。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        sandbox: Any

    async def _route_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """路由工具调用到 Sandbox（带凭证安全检查）

        如果使用 CredentialIsolatedSandbox，自动使用隔离执行。

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具执行结果列表
        """
        from src.security.credential_isolated_sandbox import CredentialIsolatedSandbox

        # 如果使用 CredentialIsolatedSandbox，使用隔离执行
        if isinstance(self.sandbox, CredentialIsolatedSandbox):
            secure_results = await self.sandbox.execute_tools_isolated(tool_calls)

            # 转换为标准格式
            return [
                {
                    "tool_call_id": result.tool_call_id,
                    "role": "tool",
                    "content": result.content,
                }
                for result in secure_results
            ]

        # 默认使用标准 Harness 执行（需要父类方法）
        # 调用 super()._route_tool_calls
        return await super()._route_tool_calls(tool_calls)  # type: ignore[misc]