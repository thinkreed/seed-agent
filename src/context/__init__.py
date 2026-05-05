"""
上下文工程模块

基于 Harness Engineering "上下文工程" 设计：
- 渐进式压缩：最新完整保留 → 稍旧轻量总结 → 更早简短摘要
- 智能裁剪：根据任务相关性过滤不相关历史
- 原始数据不丢失：Session 保留完整历史

核心组件：
- ProgressiveContextCompressor: 三层渐进压缩
- IntelligentContextPruner: 智能裁剪
- ContextEngineering: 集成管理器（在 src/context_engineering.py 中定义）

特性：
- 渐进信息损失，不丢失原始数据
- 相关性过滤，保留关键信息
- 上下文利用率提升，避免浪费 Token

公共 API 导出：
- CompressionConfig, CompressionTier, TierConfig: 压缩配置
- PruningConfig: 裁剪配置
- ProgressiveContextCompressor: 渐进式压缩器
- IntelligentContextPruner: 智能裁剪器

注意：ContextEngineering 类请从 src.context_engineering 导入
"""

# 配置类导出
# 核心类导出
from src.context._compressor import ProgressiveContextCompressor
from src.context._config import (
    RELEVANCE_THRESHOLD,
    CompressionConfig,
    CompressionTier,
    PruningConfig,
    TierConfig,
)
from src.context._pruner import IntelligentContextPruner

__all__ = [
    "RELEVANCE_THRESHOLD",
    # 配置类
    "CompressionConfig",
    "CompressionTier",
    "IntelligentContextPruner",
    # 核心类
    "ProgressiveContextCompressor",
    "PruningConfig",
    "TierConfig",
]


# 延迟导入 ContextEngineering（避免循环依赖）
def __getattr__(name: str):
    """延迟导入 ContextEngineering"""
    if name == "ContextEngineering":
        import importlib
        module = importlib.import_module("src.context_engineering")
        return module.ContextEngineering
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")