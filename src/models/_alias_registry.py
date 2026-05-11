"""ModelAliasRegistry - 模型别名映射注册表

基于 DeepSeek-TUI 的 ModelRegistry 设计：
- 别名映射：支持多个别名指向同一个模型
- 大小写保持：解析后保持用户指定的大小写
- Provider 关联：别名可指定 Provider

Wiki 知识落地 P6 (DeepSeek-TUI ModelAlias)
"""

from __future__ import annotations

import logging

from ._alias_presets import register_all_defaults
from ._alias_query import get_canonical_id, has_alias, list_aliases, list_models
from ._alias_types import ModelInfo, ProviderKind, ResolvedModel

logger = logging.getLogger(__name__)


class ModelAliasRegistry:
    """模型别名映射注册表"""

    def __init__(self) -> None:
        self._models: list[ModelInfo] = []
        self._alias_map: dict[str, int] = {}
        self._canonical_map: dict[str, int] = {}

    def register(
        self,
        canonical_id: str,
        aliases: list[str] | None = None,
        provider: ProviderKind = ProviderKind.Custom,
        supports_tools: bool = True,
        supports_reasoning: bool = False,
    ) -> None:
        """注册模型及其别名"""
        model_info = ModelInfo(
            id=canonical_id,
            provider=provider,
            aliases=aliases or [],
            supports_tools=supports_tools,
            supports_reasoning=supports_reasoning,
        )

        model_index = len(self._models)
        self._models.append(model_info)

        self._canonical_map[canonical_id.lower()] = model_index

        for alias in aliases or []:
            alias_lower = alias.lower()
            if alias_lower in self._alias_map:
                logger.warning(f"Alias '{alias}' already registered, overwriting")
            self._alias_map[alias_lower] = model_index

        logger.debug(f"Registered model: {canonical_id} with aliases: {aliases or []}")

    def resolve(
        self,
        requested: str | None,
        provider_hint: ProviderKind | None = None,
    ) -> ResolvedModel | None:
        """解析模型 ID"""
        if not requested:
            return self._get_default_model()

        requested_lower = requested.lower()

        if provider_hint:
            provider_match = self._find_provider_model(requested_lower, provider_hint)
            if provider_match is not None:
                return self._create_resolved_model(provider_match, requested)

        if requested_lower in self._alias_map:
            return self._create_resolved_model(self._alias_map[requested_lower], requested)

        if requested_lower in self._canonical_map:
            return self._create_resolved_model(self._canonical_map[requested_lower], requested)

        logger.warning(f"Model not found: {requested}")
        return None

    def _find_provider_model(self, requested_lower: str, provider: ProviderKind) -> int | None:
        for index, model in enumerate(self._models):
            if model.provider != provider:
                continue
            if model.id.lower() == requested_lower:
                return index
            for alias in model.aliases:
                if alias.lower() == requested_lower:
                    return index
        return None

    def _create_resolved_model(self, model_index: int, requested: str) -> ResolvedModel:
        model_info = self._models[model_index]
        return ResolvedModel(
            id=model_info.id,
            requested=requested,
            provider=model_info.provider,
            aliases=model_info.aliases,
            supports_tools=model_info.supports_tools,
            supports_reasoning=model_info.supports_reasoning,
        )

    def _get_default_model(self) -> ResolvedModel | None:
        if not self._models:
            return None
        return self._create_resolved_model(0, self._models[0].id)

    # 查询方法委托给 _alias_query 模块
    def list_models(self, provider: ProviderKind | None = None) -> list[ModelInfo]:
        return list_models(self, provider)

    def list_aliases(self) -> dict[str, str]:
        return list_aliases(self)

    def has_alias(self, alias: str) -> bool:
        return has_alias(self, alias)

    def get_canonical_id(self, alias: str) -> str | None:
        return get_canonical_id(self, alias)

    def register_all_defaults(self) -> None:
        register_all_defaults(self)


# 全局注册表实例
_global_registry: ModelAliasRegistry | None = None


def get_global_registry() -> ModelAliasRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ModelAliasRegistry()
        _global_registry.register_all_defaults()
    return _global_registry


def reset_global_registry() -> None:
    global _global_registry
    _global_registry = None


__all__ = ["ModelAliasRegistry", "get_global_registry", "reset_global_registry"]