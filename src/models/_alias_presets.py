"""ModelAlias 预设模型注册

基于 DeepSeek-TUI 的预设模型配置：
- DeepSeek: v4-pro, v4-flash
- Qwen: plus, turbo, max
- OpenAI: gpt-4o, gpt-4o-mini

Wiki 知识落地 P6 (DeepSeek-TUI ModelAlias)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._alias_types import ProviderKind

if TYPE_CHECKING:
    from ._alias_registry import ModelAliasRegistry

logger = logging.getLogger(__name__)


def register_deepseek_models(registry: "ModelAliasRegistry") -> None:
    """注册 DeepSeek 模型预设"""
    registry.register(
        "deepseek-v4-pro",
        aliases=["deepseek-pro", "deepseek-reasoning"],
        provider=ProviderKind.DeepSeek,
        supports_tools=True,
        supports_reasoning=True,
    )
    registry.register(
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


def register_qwen_models(registry: "ModelAliasRegistry") -> None:
    """注册 Qwen 模型预设"""
    registry.register(
        "qwen-plus",
        aliases=["qwen2-plus", "qwen-plus-latest", "qwen2.5-plus"],
        provider=ProviderKind.Qwen,
        supports_tools=True,
        supports_reasoning=False,
    )
    registry.register(
        "qwen-turbo",
        aliases=["qwen2-turbo", "qwen-turbo-latest", "qwen2.5-turbo"],
        provider=ProviderKind.Qwen,
        supports_tools=True,
        supports_reasoning=False,
    )
    registry.register(
        "qwen-max",
        aliases=["qwen2-max", "qwen-max-latest", "qwen2.5-max"],
        provider=ProviderKind.Qwen,
        supports_tools=True,
        supports_reasoning=True,
    )
    logger.info("Qwen models registered: 3 models")


def register_openai_models(registry: "ModelAliasRegistry") -> None:
    """注册 OpenAI 模型预设"""
    registry.register(
        "gpt-4o",
        aliases=["gpt4o", "gpt-4-omni"],
        provider=ProviderKind.OpenAI,
        supports_tools=True,
        supports_reasoning=False,
    )
    registry.register(
        "gpt-4o-mini",
        aliases=["gpt4o-mini", "gpt-4-omni-mini"],
        provider=ProviderKind.OpenAI,
        supports_tools=True,
        supports_reasoning=False,
    )
    logger.info("OpenAI models registered: 2 models")


def register_all_defaults(registry: "ModelAliasRegistry") -> None:
    """注册所有默认模型预设"""
    register_deepseek_models(registry)
    register_qwen_models(registry)
    register_openai_models(registry)
    logger.info(f"All default models registered: {len(registry._models)} models")


__all__ = [
    "register_deepseek_models",
    "register_qwen_models",
    "register_openai_models",
    "register_all_defaults",
]