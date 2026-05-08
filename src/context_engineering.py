"""上下文工程模块（主入口）

基于 Harness Engineering "上下文工程" 设计：
- 渐进式压缩：最新完整保留 → 稍旧轻量总结 → 更早简短摘要
- 智能裁剪：根据任务相关性过滤不相关历史
- 原始数据不丢失：Session 保留完整历史

此文件作为公共 API 入口，具体实现拆分到子模块：
- src/context/_config.py: 配置类
- src/context/_compressor.py: ProgressiveContextCompressor
- src/context/_pruner.py: IntelligentContextPruner
- src/context/_manager.py: ContextEngineering 集成管理器

公共 API 导出（保持向后兼容）：
- CompressionConfig, CompressionTier, TierConfig: 压缩配置
- PruningConfig: 裁剪配置
- ProgressiveContextCompressor: 渐进式压缩器
- IntelligentContextPruner: 智能裁剪器
- ContextEngineering: 集成管理器
"""

# 从子模块导入核心类
from src.context._compressor import ProgressiveContextCompressor
from src.context._config import (
    CompressionConfig,
    CompressionTier,
    PruningConfig,
    TierConfig,
)
from src.context._manager import ContextEngineering
from src.context._pruner import IntelligentContextPruner

# 重新导出子模块的公共类（保持向后兼容）
# 用户可以从 context_engineering 或 context 包导入
__all__ = [
    # 配置类
    "CompressionConfig",
    "CompressionTier",
    # 集成管理器
    "ContextEngineering",
    "IntelligentContextPruner",
    # 核心类
    "ProgressiveContextCompressor",
    "PruningConfig",
    "TierConfig",
]