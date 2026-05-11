"""ModelAliasRegistry - 模型别名映射注册表

基于 DeepSeek-TUI 的 ModelRegistry 设计：
- 别名映射：支持多个别名指向同一个模型
- 大小写保持：解析后保持用户指定的大小写
- Provider 关联：别名可指定 Provider
- 快速解析：高效的别名查找

使用示例:
    registry = ModelAliasRegistry()
    registry.register("deepseek-v4-flash", ["deepseek-chat", "deepseek-reasoner", "deepseek-r1"])
    registry.register("qwen-plus", ["qwen2-plus", "qwen-plus-latest"])
    
    resolved = registry.resolve("deepseek-chat")  # -> ResolvedModel(id="deepseek-v4-flash", requested="deepseek-chat")
    resolved.id  # "deepseek-v4-flash" (规范化 ID)
    resolved.requested  # "deepseek-chat" (用户原始输入)

设计模式:
- Registry Pattern: 统一注册和查询
- Alias Normalization: 不区分大小写查找
- Case Preservation: 解析后保持原始大小写

Wiki 知识落地 P6 (DeepSeek-TUI ModelAlias):
- alias_map: 别名到规范 ID 的映射
- preserve_requested_model_id_case: 保持用户指定的大小写
- provider_specific_match: 支持 Provider 指定的别名
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProviderKind(Enum):
    """提供商类型枚举

    基于 DeepSeek-TUI 的 ProviderKind 设计：
    - DeepSeek: DeepSeek 官方 API
    - OpenAI: OpenAI API
    - Qwen: 阿里云百炼 API
    - Anthropic: Anthropic Claude API
    - Custom: 自定义提供商
    """

    DeepSeek = "deepseek"
    OpenAI = "openai"
    Qwen = "qwen"
    Anthropic = "anthropic"
    Custom = "custom"


@dataclass
class ResolvedModel:
    """解析后的模型信息

    基于 DeepSeek-TUI 的 ModelResolution 设计：
    - id: 规范化模型 ID
    - requested: 用户原始输入（保持大小写）
    - provider: 提供商类型
    - supports_tools: 是否支持工具调用
    - supports_reasoning: 是否支持推理模式

    Attributes:
        id: 规范化模型 ID
        requested: 用户原始输入
        provider: 提供商类型
        aliases: 该模型的已知别名列表
        supports_tools: 是否支持工具调用
        supports_reasoning: 是否支持推理模式
    """

    id: str
    requested: str
    provider: ProviderKind = ProviderKind.Custom
    aliases: list[str] = field(default_factory=list)
    supports_tools: bool = True
    supports_reasoning: bool = False

    def __str__(self) -> str:
        return f"ResolvedModel(id={self.id}, requested={self.requested}, provider={self.provider.value})"


@dataclass
class ModelInfo:
    """模型信息

    基于 DeepSeek-TUI 的 ModelInfo 设计：
    - id: 规范化模型 ID
    - provider: 提供商类型
    - aliases: 别名列表
    - supports_tools: 是否支持工具调用
    - supports_reasoning: 是否支持推理模式
    """

    id: str
    provider: ProviderKind
    aliases: list[str] = field(default_factory=list)
    supports_tools: bool = True
    supports_reasoning: bool = False


class ModelAliasRegistry:
    """模型别名映射注册表

    基于 DeepSeek-TUI 的 ModelRegistry 设计：
    - 别名映射：支持多个别名指向同一个模型
    - 大小写保持：解析后保持用户指定的大小写
    - Provider 关联：别名可指定 Provider
    - 快速解析：高效的别名查找

    Attributes:
        _models: 规范化模型列表
        _alias_map: 别名到模型索引的映射（小写）
    """

    def __init__(self) -> None:
        """初始化注册表"""
        self._models: list[ModelInfo] = []
        self._alias_map: dict[str, int] = {}  # 小写别名 -> 模型索引
        self._canonical_map: dict[str, int] = {}  # 小写规范 ID -> 模型索引

    def register(
        self,
        canonical_id: str,
        aliases: list[str] | None = None,
        provider: ProviderKind = ProviderKind.Custom,
        supports_tools: bool = True,
        supports_reasoning: bool = False,
    ) -> None:
        """注册模型及其别名

        Args:
            canonical_id: 规范化模型 ID
            aliases: 别名列表（可选）
            provider: 提供商类型
            supports_tools: 是否支持工具调用
            supports_reasoning: 是否支持推理模式
        """
        # 创建模型信息
        model_info = ModelInfo(
            id=canonical_id,
            provider=provider,
            aliases=aliases or [],
            supports_tools=supports_tools,
            supports_reasoning=supports_reasoning,
        )

        # 添加到模型列表
        model_index = len(self._models)
        self._models.append(model_info)

        # 注册规范 ID（小写）
        canonical_lower = canonical_id.lower()
        self._canonical_map[canonical_lower] = model_index

        # 注册别名（小写）
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
        """解析模型 ID

        Args:
            requested: 用户请求的模型 ID（可以是别名）
            provider_hint: 提供商提示（可选）

        Returns:
            ResolvedModel: 解析后的模型信息，若未找到返回 None
        """
        if not requested:
            return self._get_default_model()

        requested_lower = requested.lower()

        # 1. 尝试 Provider 指定匹配（如果有 hint）
        if provider_hint:
            provider_match = self._find_provider_model(requested_lower, provider_hint)
            if provider_match is not None:
                return self._create_resolved_model(provider_match, requested)

        # 2. 尝试别名映射查找
        if requested_lower in self._alias_map:
            model_index = self._alias_map[requested_lower]
            return self._create_resolved_model(model_index, requested)

        # 3. 尝试规范 ID 查找
        if requested_lower in self._canonical_map:
            model_index = self._canonical_map[requested_lower]
            return self._create_resolved_model(model_index, requested)

        # 4. 未找到，返回 None
        logger.warning(f"Model not found: {requested}")
        return None

    def _find_provider_model(self, requested_lower: str, provider: ProviderKind) -> int | None:
        """查找 Provider 指定的模型

        Args:
            requested_lower: 小写请求 ID
            provider: 提供商类型

        Returns:
            int: 模型索引，若未找到返回 None
        """
        for index, model in enumerate(self._models):
            if model.provider != provider:
                continue
            # 匹配规范 ID 或别名
            if model.id.lower() == requested_lower:
                return index
            for alias in model.aliases:
                if alias.lower() == requested_lower:
                    return index
        return None

    def _create_resolved_model(self, model_index: int, requested: str) -> ResolvedModel:
        """创建解析后的模型信息

        Args:
            model_index: 模型索引
            requested: 用户原始输入

        Returns:
            ResolvedModel: 解析后的模型信息
        """
        model_info = self._models[model_index]
        return ResolvedModel(
            id=model_info.id,
            requested=requested,  # 保持用户原始大小写
            provider=model_info.provider,
            aliases=model_info.aliases,
            supports_tools=model_info.supports_tools,
            supports_reasoning=model_info.supports_reasoning,
        )

    def _get_default_model(self) -> ResolvedModel | None:
        """获取默认模型

        Returns:
            ResolvedModel: 默认模型，若无注册模型返回 None
        """
        if not self._models:
            return None
        # 返回第一个注册的模型作为默认
        return self._create_resolved_model(0, self._models[0].id)

    def list_models(self, provider: ProviderKind | None = None) -> list[ModelInfo]:
        """列出所有模型

        Args:
            provider: 提供商过滤（可选）

        Returns:
            list[ModelInfo]: 模型信息列表
        """
        if provider is None:
            return self._models.copy()
        return [m for m in self._models if m.provider == provider]

    def list_aliases(self) -> dict[str, str]:
        """列出所有别名映射

        Returns:
            dict[str, str]: 别名到规范 ID 的映射
        """
        return {
            alias: self._models[index].id
            for alias, index in self._alias_map.items()
        }

    def has_alias(self, alias: str) -> bool:
        """检查别名是否存在

        Args:
            alias: 别名

        Returns:
            bool: 是否存在
        """
        return alias.lower() in self._alias_map

    def get_canonical_id(self, alias: str) -> str | None:
        """获取别名的规范 ID

        Args:
            alias: 别名

        Returns:
            str: 规范 ID，若未找到返回 None
        """
        model_index = self._alias_map.get(alias.lower())
        if model_index is None:
            return None
        return self._models[model_index].id

    # === 预设模型注册 ===

    def register_deepseek_models(self) -> None:
        """注册 DeepSeek 模型预设

        基于 DeepSeek-TUI 的模型别名表：
        - deepseek-v4-pro: 推理模型
        - deepseek-v4-flash: 快速模型（别名：deepseek-chat, deepseek-reasoner）
        """
        self.register(
            "deepseek-v4-pro",
            aliases=["deepseek-pro", "deepseek-reasoning"],
            provider=ProviderKind.DeepSeek,
            supports_tools=True,
            supports_reasoning=True,
        )
        self.register(
            "deepseek-v4-flash",
            aliases=[
                "deepseek-chat",
                "deepseek-reasoner",
                "deepseek-r1",
                "deepseek-v3",
                "deepseek-v3.2",
            ],
            provider=ProviderKind.DeepSeek,
            supports_tools=True,
            supports_reasoning=False,
        )
        logger.info("DeepSeek models registered: 2 models")

    def register_qwen_models(self) -> None:
        """注册 Qwen 模型预设"""
        self.register(
            "qwen-plus",
            aliases=["qwen2-plus", "qwen-plus-latest", "qwen2.5-plus"],
            provider=ProviderKind.Qwen,
            supports_tools=True,
            supports_reasoning=False,
        )
        self.register(
            "qwen-turbo",
            aliases=["qwen2-turbo", "qwen-turbo-latest", "qwen2.5-turbo"],
            provider=ProviderKind.Qwen,
            supports_tools=True,
            supports_reasoning=False,
        )
        self.register(
            "qwen-max",
            aliases=["qwen2-max", "qwen-max-latest", "qwen2.5-max"],
            provider=ProviderKind.Qwen,
            supports_tools=True,
            supports_reasoning=True,
        )
        logger.info("Qwen models registered: 3 models")

    def register_openai_models(self) -> None:
        """注册 OpenAI 模型预设"""
        self.register(
            "gpt-4o",
            aliases=["gpt4o", "gpt-4-omni"],
            provider=ProviderKind.OpenAI,
            supports_tools=True,
            supports_reasoning=False,
        )
        self.register(
            "gpt-4o-mini",
            aliases=["gpt4o-mini", "gpt-4-omni-mini"],
            provider=ProviderKind.OpenAI,
            supports_tools=True,
            supports_reasoning=False,
        )
        logger.info("OpenAI models registered: 2 models")

    def register_all_defaults(self) -> None:
        """注册所有默认模型预设"""
        self.register_deepseek_models()
        self.register_qwen_models()
        self.register_openai_models()
        logger.info(f"All default models registered: {len(self._models)} models")


# 全局注册表实例（可选）
_global_registry: ModelAliasRegistry | None = None


def get_global_registry() -> ModelAliasRegistry:
    """获取全局注册表实例

    Returns:
        ModelAliasRegistry: 全局注册表实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ModelAliasRegistry()
        _global_registry.register_all_defaults()
    return _global_registry


def reset_global_registry() -> None:
    """重置全局注册表"""
    global _global_registry
    _global_registry = None


__all__ = [
    "ModelAliasRegistry",
    "ModelInfo",
    "ProviderKind",
    "ResolvedModel",
    "get_global_registry",
    "reset_global_registry",
]