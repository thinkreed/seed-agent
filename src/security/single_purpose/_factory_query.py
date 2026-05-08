"""
单用途工具工厂 - 查询和 Schema 模块

功能:
- 获取工具配置
- 获取工具名称列表
- 生成 LLM schema
- 权限过滤
"""

from typing import Any

from src.security.single_purpose._config import (
    SINGLE_PURPOSE_TOOLS,
    SinglePurposeToolConfig,
    SinglePurposeToolRisk,
)


def get_tool_config(tool_name: str) -> SinglePurposeToolConfig | None:
    """获取工具配置"""
    return SINGLE_PURPOSE_TOOLS.get(tool_name)


def get_all_tool_names() -> list[str]:
    """获取所有工具名称"""
    return list(SINGLE_PURPOSE_TOOLS.keys())


def get_tools_by_risk(risk: SinglePurposeToolRisk) -> list[str]:
    """获取指定风险等级的工具"""
    return [
        name
        for name, config in SINGLE_PURPOSE_TOOLS.items()
        if config.risk == risk
    ]


def get_tool_schema(tool_name: str) -> dict[str, Any]:
    """获取工具 schema（供 LLM 使用）

    Args:
        tool_name: 工具名称

    Returns:
        OpenAI function calling 格式的 schema

    Raises:
        ValueError: 工具不存在
    """
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


def get_allowed_tool_names(
    allow_risky_tools: bool,
    allow_dangerous_tools: bool,
) -> list[str]:
    """获取允许的工具名称

    Args:
        allow_risky_tools: 是否允许 risky 级别工具
        allow_dangerous_tools: 是否允许 dangerous 级别工具

    Returns:
        允许使用的工具名称列表
    """
    allowed = []

    for name, config in SINGLE_PURPOSE_TOOLS.items():
        # 检查风险等级
        if (
            config.risk == SinglePurposeToolRisk.DANGEROUS
            and not allow_dangerous_tools
        ):
            continue
        if (
            config.risk == SinglePurposeToolRisk.RISKY
            and not allow_risky_tools
        ):
            continue

        # 检查 block_by_default
        if config.block_by_default and not allow_dangerous_tools:
            continue

        allowed.append(name)

    return allowed


def get_all_tool_schemas(
    allow_risky_tools: bool,
    allow_dangerous_tools: bool,
) -> list[dict[str, Any]]:
    """获取所有工具 schema

    Args:
        allow_risky_tools: 是否允许 risky 级别工具
        allow_dangerous_tools: 是否允许 dangerous 级别工具

    Returns:
        所有允许工具的 schema 列表
    """
    schemas = []
    allowed_names = get_allowed_tool_names(allow_risky_tools, allow_dangerous_tools)

    for tool_name in allowed_names:
        try:
            schemas.append(get_tool_schema(tool_name))
        except ValueError:
            continue

    return schemas