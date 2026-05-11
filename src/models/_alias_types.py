"""ModelAlias 类型定义

基于 DeepSeek-TUI 的类型设计：
- ProviderKind: 提供商类型枚举
- ResolvedModel: 解析后的模型信息
- ModelInfo: 模型元数据

Wiki 知识落地 P6 (DeepSeek-TUI ModelAlias)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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


__all__ = ["ProviderKind", "ResolvedModel", "ModelInfo"]