"""
单用途工具工厂

核心功能:
- 创建单用途工具函数
- 参数验证
- 风险预设
- 安全执行
"""

import logging
from collections.abc import Callable
from typing import Any

from src.security.single_purpose._config import (
    SINGLE_PURPOSE_TOOLS,
    SinglePurposeToolConfig,
    SinglePurposeToolRisk,
)
from src.security.single_purpose._implementations import TOOL_IMPLEMENTATIONS
from src.security.single_purpose._validation import (
    request_confirmation,
    validate_args,
)

logger = logging.getLogger(__name__)


class SinglePurposeToolFactory:
    """单用途工具工厂

    核心功能:
    - 创建单用途工具函数
    - 参数验证
    - 风险预设
    - 安全执行

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
        """初始化工具工厂

        Args:
            allow_risky_tools: 是否允许 risky 级别工具
            allow_dangerous_tools: 是否允许 dangerous 级别工具
            confirmation_callback: 用户确认回调函数
        """
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

        # 检查工具是否被允许
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
            """工具执行函数"""
            # 1. 参数验证
            validated_args = validate_args(config, kwargs)

            # 2. 用户确认（如需要）
            if config.require_confirmation:
                confirmed = request_confirmation(
                    tool_name, validated_args, self._confirmation_callback
                )
                if not confirmed:
                    return f"[CANCELLED] User cancelled {tool_name}"

            # 3. 执行操作
            try:
                return self._execute_tool(tool_name, validated_args)
            except Exception as e:
                logger.exception(f"Tool {tool_name} failed: {e}")
                return f"[ERROR] {tool_name} failed: {type(e).__name__}: {str(e)[:200]}"

        # 设置函数属性
        tool_func.__name__ = tool_name
        tool_func.__doc__ = config.description
        tool_func._tool_config = config  # type: ignore

        return tool_func

    def get_tool_config(self, tool_name: str) -> SinglePurposeToolConfig | None:
        """获取工具配置"""
        return SINGLE_PURPOSE_TOOLS.get(tool_name)

    def get_all_tool_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(SINGLE_PURPOSE_TOOLS.keys())

    def get_tools_by_risk(self, risk: SinglePurposeToolRisk) -> list[str]:
        """获取指定风险等级的工具"""
        return [
            name
            for name, config in SINGLE_PURPOSE_TOOLS.items()
            if config.risk == risk
        ]

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        """获取工具 schema（供 LLM 使用）"""
        config = SINGLE_PURPOSE_TOOLS.get(tool_name)
        if config is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        # 构建 OpenAI function calling 格式的 schema
        properties: dict[str, Any] = {}
        required: list[str] = []

        for arg_name, arg_schema in config.args_schema.items():
            properties[arg_name] = {
                "type": arg_schema.get("type", "string"),
                "description": arg_schema.get("description", ""),
            }
            if arg_schema.get("required"):
                required.append(arg_name)

        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": config.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        """获取所有工具 schema"""
        schemas = []
        for tool_name in self.get_allowed_tool_names():
            try:
                schemas.append(self.get_tool_schema(tool_name))
            except ValueError:
                continue
        return schemas

    def get_allowed_tool_names(self) -> list[str]:
        """获取允许的工具名称"""
        allowed = []

        for name, config in SINGLE_PURPOSE_TOOLS.items():
            # 检查风险等级
            if (
                config.risk == SinglePurposeToolRisk.DANGEROUS
                and not self._allow_dangerous_tools
            ):
                continue
            if (
                config.risk == SinglePurposeToolRisk.RISKY
                and not self._allow_risky_tools
            ):
                continue

            # 检查 block_by_default
            if config.block_by_default and not self._allow_dangerous_tools:
                continue

            allowed.append(name)

        return allowed

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """执行工具操作

        路由到对应的实现函数
        """
        impl_func = TOOL_IMPLEMENTATIONS.get(tool_name)
        if impl_func is None:
            raise RuntimeError(f"No implementation for tool: {tool_name}")

        return impl_func(args)

    def set_confirmation_callback(
        self,
        callback: Callable[[str, dict[str, Any]], bool],
    ) -> None:
        """设置用户确认回调函数"""
        self._confirmation_callback = callback
        logger.info("Confirmation callback set")

    def set_allow_risky_tools(self, allow: bool) -> None:
        """设置是否允许 risky 工具"""
        self._allow_risky_tools = allow
        logger.info(f"Allow risky tools set to: {allow}")

    def set_allow_dangerous_tools(self, allow: bool) -> None:
        """设置是否允许 dangerous 工具"""
        self._allow_dangerous_tools = allow
        logger.info(f"Allow dangerous tools set to: {allow}")