"""
Harness 包

基于 Harness Engineering "三件套解耦架构" 设计：
- Harness 是控制器（双手），驱动运行循环
- 从 Session 拉取上下文 → 调用 LLM API → 路由工具调用
- 本身无状态，可随时创建、销毁、替换
- 不持有对话历史，只通过 SessionEventStream 访问

公共接口：
- Harness: 主控制器类
- HarnessManager: 多实例管理器
- CycleResult: 单轮循环结果类型
- ToolExecutionMetrics: 工具执行指标类型
- MaxIterationsExceededError: 最大迭代次数错误

内部模块（私有，使用 _ 前缀）：
- _metrics: 指标和 OpenTelemetry Span
- _write_conflict: 写冲突检测
- _lifecycle_hooks: 钩子触发和上下文构建
- _single_tool: 单工具执行
- _tool_router: 工具路由
- _context_builder: 上下文构建
- _streaming: 流式处理
- _resume: 恢复执行
- _manager: HarnessManager 类
"""

from typing import Any

# 导入 HarnessManager
from ._manager import MAX_ITERATIONS, HarnessManager

# 从子模块导入类型
from ._metrics import ToolExecutionMetrics

__all__ = [
    "MAX_ITERATIONS",
    "CycleResult",
    "Harness",
    "HarnessManager",
    "MaxIterationsExceededError",
    "ToolExecutionMetrics",
]

# 使用特殊路径导入 src/harness.py 中的类（避免循环导入）
_Harness_module = None


def _load_harness_module():
    """加载 src/harness.py 模块"""
    global _Harness_module
    if _Harness_module is None:
        import importlib.util
        import os
        harness_file = os.path.join(os.path.dirname(__file__), "..", "harness.py")
        spec = importlib.util.spec_from_file_location("_harness_main", harness_file)
        if spec and spec.loader:
            _Harness_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_Harness_module)
        else:
            raise ImportError("Failed to load Harness module")
    return _Harness_module


def __getattr__(name: str) -> Any:
    """延迟导入 Harness、CycleResult、MaxIterationsExceededError"""
    if name in ("Harness", "CycleResult", "MaxIterationsExceededError"):
        module = _load_harness_module()
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")