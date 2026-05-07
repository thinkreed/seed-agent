"""
工具系统模块

负责:
1. 工具注册与发现 (ToolRegistry、动态加载)
2. 工具调用验证 (参数检查、权限控制、路径安全)
3. 工具并发执行 (asyncio.gather、路径重叠防护)
4. 工具结果处理 (输出截断、错误格式化)

核心组件:
- ToolRegistry: 全局工具注册表
- builtin_tools: 内置工具实现
- memory_tools: 记忆系统工具
- skill_loader: 技能加载器
- session_db: 会话数据库

Wiki 知识落地 (基于 Qwen-Code 工具系统设计):
- ToolKind: 工具分类枚举 (Read/Edit/Delete/Execute/Search 等)
- PermissionDecision: 权限三级模式 (allow/ask/deny)
- MUTATOR_KINDS: 具有副作用的工具类型
- CONCURRENCY_SAFE_KINDS: 可安全并发执行的工具类型
- ToolFactory: 延迟加载工厂函数类型 (P2 新增)
- register_factory/ensure_tool/warm_all: 延迟加载机制 (P2 新增)

Wiki 知识落地 P3 (基于 DeepSeek-TUI 工具系统设计):
- ToolCapability: 工具能力声明枚举 (ReadOnly/WritesFiles/ExecutesCode 等)
- ApprovalRequirement: 三级审批需求 (Auto/Suggest/Required)
- CAPABILITY_APPROVAL_MAP: 能力到审批需求的映射

版本: v2.4 (Wiki 知识落地 P3 版)
"""

from ._registry import ToolFactory, ToolRegistry
from ._types import (
    CAPABILITY_APPROVAL_MAP,
    CONCURRENCY_SAFE_KINDS,
    MUTATOR_KINDS,
    READ_ONLY_CAPABILITIES,
    SANDBOX_REQUIRED_CAPABILITIES,
    ApprovalRequirement,
    PermissionDecision,
    ToolCapability,
    ToolKind,
)


__all__ = [
    # 工具分类系统 (Wiki 知识落地 - Qwen-Code)
    "ToolKind",
    "PermissionDecision",
    "MUTATOR_KINDS",
    "CONCURRENCY_SAFE_KINDS",
    # 延迟加载机制 (Wiki 知识落地 P2)
    "ToolFactory",
    # Wiki 知识落地 P3 (DeepSeek-TUI)
    "ToolCapability",
    "ApprovalRequirement",
    "CAPABILITY_APPROVAL_MAP",
    "SANDBOX_REQUIRED_CAPABILITIES",
    "READ_ONLY_CAPABILITIES",
    # 核心类
    "ToolRegistry",
]