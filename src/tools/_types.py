"""
工具系统类型定义

Wiki 知识落地 (基于 Qwen-Code 工具系统设计):
- ToolKind: 工具分类枚举 (Read/Edit/Delete/Execute/Search 等)
- PermissionDecision: 权限三级模式 (allow/ask/deny)
- MUTATOR_KINDS: 具有副作用的工具类型
- CONCURRENCY_SAFE_KINDS: 可安全并发执行的工具类型
"""

from enum import Enum


class ToolKind(Enum):
    """工具分类枚举

    基于 Qwen-Code 的 Kind 设计，将工具按操作类型分类：
    - Read: 只读操作（文件读取、搜索）
    - Edit: 编辑操作（文件修改）
    - Delete: 删除操作（文件删除）
    - Execute: 执行操作（代码执行、Shell 命令）
    - Search: 搜索操作（grep、glob）
    - Memory: 记忆操作（读写记忆）
    - Agent: 子代理操作（spawn subagent）
    - Other: 其他操作

    用途：
    - 权限检查：不同类型有不同的默认权限
    - 并发控制：判断是否可以并发执行
    - 副作用检测：判断是否需要用户确认
    """

    Read = "read"
    Edit = "edit"
    Delete = "delete"
    Execute = "execute"
    Search = "search"
    Memory = "memory"
    Agent = "agent"
    Other = "other"


class PermissionDecision(Enum):
    """权限决策枚举

    基于 Qwen-Code 的三级权限模式：
    - allow: 固有安全，直接执行无需确认
    - ask: 需要用户确认后执行
    - deny: 安全违规，拒绝执行

    用途：
    - 工具调用前的权限检查
    - 用户确认流程的决策
    - 安全策略的实现
    """

    Allow = "allow"
    Ask = "ask"
    Deny = "deny"


# 具有副作用的工具类型（需要用户确认）
MUTATOR_KINDS: list[ToolKind] = [
    ToolKind.Edit,
    ToolKind.Delete,
    ToolKind.Execute,
    ToolKind.Memory,
]

# 可安全并发执行的工具类型（纯读取，无写入）
CONCURRENCY_SAFE_KINDS: set[ToolKind] = {
    ToolKind.Read,
    ToolKind.Search,
}


__all__ = [
    "ToolKind",
    "PermissionDecision",
    "MUTATOR_KINDS",
    "CONCURRENCY_SAFE_KINDS",
]