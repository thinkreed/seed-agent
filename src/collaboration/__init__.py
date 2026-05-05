"""多智能体协作模块

基于 Harness Engineering "三件套解耦架构" 设计的三种协作模式：
- 多脑一手：多个 Claude 共享一个 Sandbox
- 一脑多手：一个 Claude 控制多个 Sandbox
- 多脑多手：多个 Claude 各有 Sandbox，通过 Session 协调

核心组件：
- MultiBrainOneHandOrchestrator: 多角度分析同一份代码
- OneBrainMultiHandOrchestrator: 跨环境执行任务
- MultiBrainMultiHandOrchestrator: Session 协调的复杂任务
- InterAgentMessageBus: 智能体间消息传递总线

公共接口导出模块，提供向后兼容的 API。

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

from typing import TYPE_CHECKING

# 从内部模块导出编排器类
from src.collaboration._message_bus import InterAgentMessageBus
from src.collaboration._multi_brain_multi_hand import MultiBrainMultiHandOrchestrator
from src.collaboration._multi_brain_one_hand import MultiBrainOneHandOrchestrator
from src.collaboration._one_brain_multi_hand import OneBrainMultiHandOrchestrator

# 从内部模块导出公共类型
from src.collaboration._types import (
    AgentInstance,
    AnalysisResult,
    CollaborationMode,
    CoordinationResult,
    ExecutionResult,
)

if TYPE_CHECKING:
    from src.tools import ToolRegistry


__all__ = [
    "AgentInstance",
    "AnalysisResult",
    # 数据类型
    "CollaborationMode",
    "CoordinationResult",
    "ExecutionResult",
    "InterAgentMessageBus",
    "MultiBrainMultiHandOrchestrator",
    # 编排器类
    "MultiBrainOneHandOrchestrator",
    "OneBrainMultiHandOrchestrator",
    # 工具注册函数
    "register_collaboration_tools",
]


def register_collaboration_tools(registry: "ToolRegistry") -> None:
    """注册协作工具到 Registry

    Args:
        registry: 工具注册表
    """
    # 导入并注册协作工具
    from src.tools.collaboration_tools import register_tools

    register_tools(registry)
