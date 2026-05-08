"""
单用途工具工厂

核心功能:
- 创建单用途工具函数
- 参数验证、风险预设、安全执行
"""

import logging
from collections.abc import Callable
from typing import Any

from src.security.single_purpose._config import (
    SINGLE_PURPOSE_TOOLS,
    SinglePurposeToolConfig,
    SinglePurposeToolRisk,
)
from src.security.single_purpose._factory_query import (
    get_allowed_tool_names,
    get_all_tool_schemas,
    get_all_tool_names,
    get_tool_config,
    get_tool_schema,
    get_tools_by_risk,
)
from src.security.single_purpose._implementations import TOOL_IMPLEMENTATIONS
from src.security.single_purpose._validation import (
    request_confirmation,
    validate_args,
)

logger = logging.getLogger(__name__)


class SinglePurposeToolFactory:
    """单用途工具工厂

    Example:
        factory = SinglePurposeToolFactory()
        tool_func = factory.create_tool("read_file_content")
        result = tool_func(path="/tmp/test.txt")
    """

    def __init__(
        self,
        allow_risky_tools: bool = True,
        allow_dangerous_tools: bool = False,
        confirmation_callback: Callable[[str, dict], bool] | None = None,
    ):
        self._allow_risky_tools = allow_risky_tools
        self._allow_dangerous_tools = allow_dangerous_tools
        self._confirmation_callback = confirmation_callback
        logger.info(
            f"SinglePurposeToolFactory initialized: "
            f"allow_risky={allow_risky_tools}, allow_dangerous={allow_dangerous_tools}"
        )

    def create_tool(self, tool_name: str) -> Callable:
        """创建单用途工具

        Args:
            tool_name: 工具名称
        Returns:
            工具函数
        Raises:
            ValueError: 工具不存在或被禁止
        """
        config = SINGLE_PURPOSE_TOOLS.get(tool_name)
        if config is None:
            raise ValueError(f"Unknown single-purpose tool: {tool_name}")

        if config.block_by_default and not self._allow_dangerous_tools:
            raise ValueError(f"Tool {tool_name} is blocked by default security policy")

        if (
            config.risk == SinglePurposeToolRisk.DANGEROUS
            and not self._allow_dangerous_tools
        ):
            raise ValueError(f"Tool {tool_name} requires dangerous tool permission")

        if (
            config.risk == SinglePurposeToolRisk.RISKY
            and not self._allow_risky_tools
        ):
            raise ValueError(f"Tool {tool_name} requires risky tool permission")

        def tool_func(**kwargs) -> str:
            validated_args = validate_args(config, kwargs)
            if config.require_confirmation:
                confirmed = request_confirmation(
                    tool_name, validated_args, self._confirmation_callback
                )
                if not confirmed:
                    return f"[CANCELLED] User cancelled {tool_name}"
            try:
                return self._execute_tool(tool_name, validated_args)
            except Exception as e:
                logger.exception(f"Tool {tool_name} failed: {e}")
                return f"[ERROR] {tool_name} failed: {type(e).__name__}: {str(e)[:200]}"

        tool_func.__name__ = tool_name
        tool_func.__doc__ = config.description
        tool_func._tool_config = config  # type: ignore
        return tool_func

    # 查询方法（委托给 _factory_query）
    get_tool_config = staticmethod(get_tool_config)
    get_all_tool_names = staticmethod(get_all_tool_names)
    get_tools_by_risk = staticmethod(get_tools_by_risk)
    get_tool_schema = staticmethod(get_tool_schema)

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        """获取所有工具 schema"""
        return get_all_tool_schemas(self._allow_risky_tools, self._allow_dangerous_tools)

    def get_allowed_tool_names(self) -> list[str]:
        """获取允许的工具名称"""
        return get_allowed_tool_names(self._allow_risky_tools, self._allow_dangerous_tools)

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """执行工具操作"""
        impl_func = TOOL_IMPLEMENTATIONS.get(tool_name)
        if impl_func is None:
            raise RuntimeError(f"No implementation for tool: {tool_name}")
        return impl_func(args)

    def set_confirmation_callback(self, callback: Callable[[str, dict[str, Any]], bool]) -> None:
        self._confirmation_callback = callback
        logger.info("Confirmation callback set")

    def set_allow_risky_tools(self, allow: bool) -> None:
        self._allow_risky_tools = allow
        logger.info(f"Allow risky tools set to: {allow}")

    def set_allow_dangerous_tools(self, allow: bool) -> None:
        self._allow_dangerous_tools = allow
        logger.info(f"Allow dangerous tools set to: {allow}")