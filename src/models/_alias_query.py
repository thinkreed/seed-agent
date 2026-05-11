"""ModelAlias 查询方法

提取自 ModelAliasRegistry 的查询相关方法：
- list_models: 列出模型
- list_aliases: 列出别名映射
- has_alias: 检查别名存在
- get_canonical_id: 获取规范 ID

Wiki 知识落地 P6 (DeepSeek-TUI ModelAlias)
"""

from __future__ import annotations

from ._alias_types import ModelInfo, ProviderKind


def list_models(registry: "ModelAliasRegistry", provider: ProviderKind | None = None) -> list[ModelInfo]:
    """列出所有模型

    Args:
        registry: ModelAliasRegistry 实例
        provider: 提供商过滤（可选）

    Returns:
        list[ModelInfo]: 模型信息列表
    """
    if provider is None:
        return registry._models.copy()
    return [m for m in registry._models if m.provider == provider]


def list_aliases(registry: "ModelAliasRegistry") -> dict[str, str]:
    """列出所有别名映射

    Args:
        registry: ModelAliasRegistry 实例

    Returns:
        dict[str, str]: 别名到规范 ID 的映射
    """
    return {
        alias: registry._models[index].id
        for alias, index in registry._alias_map.items()
    }


def has_alias(registry: "ModelAliasRegistry", alias: str) -> bool:
    """检查别名是否存在

    Args:
        registry: ModelAliasRegistry 实例
        alias: 别名

    Returns:
        bool: 是否存在
    """
    return alias.lower() in registry._alias_map


def get_canonical_id(registry: "ModelAliasRegistry", alias: str) -> str | None:
    """获取别名的规范 ID

    Args:
        registry: ModelAliasRegistry 实例
        alias: 别名

    Returns:
        str: 规范 ID，若未找到返回 None
    """
    model_index = registry._alias_map.get(alias.lower())
    if model_index is None:
        return None
    return registry._models[model_index].id


__all__ = ["list_models", "list_aliases", "has_alias", "get_canonical_id"]