"""
安全沙盒 - SecureSandbox

集成风险分类、渐进式扩展、单用途工具的完整安全沙盒

核心特性:
- 基于风险分类的工具执行控制
- 渐进式工具扩展
- 单用途工具替代通用 Shell
- 用户确认机制
- 执行历史追溯

参考来源: Harness Engineering "工具与权限"

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容

模块结构:
- _secure_sandbox_types.py: 类型定义（SecureExecutionResult）
- _secure_sandbox_execution.py: 执行逻辑（安全检查、工具执行）
- _secure_sandbox_core.py: 核心类（SecureSandbox）
"""

# 从类型模块导入（向后兼容）
from src.security._secure_sandbox_types import SecureExecutionResult

# 从核心模块导入主类（向后兼容）
from src.security._secure_sandbox_core import SecureSandbox

__all__ = [
    "SecureExecutionResult",
    "SecureSandbox",
]