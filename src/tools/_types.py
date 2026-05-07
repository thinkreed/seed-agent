"""
工具系统类型定义

Wiki 知识落地 (基于 Qwen-Code 工具系统设计):
- ToolKind: 工具分类枚举 (Read/Edit/Delete/Execute/Search 等)
- PermissionDecision: 权限三级模式 (allow/ask/deny)
- MUTATOR_KINDS: 具有副作用的工具类型
- CONCURRENCY_SAFE_KINDS: 可安全并发执行的工具类型

Wiki 知识落地 P3 (基于 DeepSeek-TUI 工具系统设计):
- ToolCapability: 工具能力声明枚举 (ReadOnly/WritesFiles/ExecutesCode 等)
- ApprovalRequirement: 三级审批需求 (Auto/Suggest/Required)
- CAPABILITY_PERMISSION_MAP: 能力到权限的映射
"""

from enum import Enum


class ToolCapability(Enum):
    """工具能力声明枚举

    基于 DeepSeek-TUI 的 ToolCapability 设计，声明工具的能力特性：
    - ReadOnly: 只读操作（无状态修改）
    - WritesFiles: 文件写入操作
    - ExecutesCode: 执行代码/命令
    - Network: 网络请求操作
    - Sandboxable: 可沙箱隔离执行
    - RequiresApproval: 需要显式审批（无论信任模式）

    用途：
    - 更细粒度的能力声明（与 ToolKind互补）
    - 安全策略路由（决定是否需要沙箱）
    - 审批流程定制（不同能力不同审批级别）
    """

    ReadOnly = "read_only"
    WritesFiles = "writes_files"
    ExecutesCode = "executes_code"
    Network = "network"
    Sandboxable = "sandboxable"
    RequiresApproval = "requires_approval"


class ApprovalRequirement(Enum):
    """三级审批需求枚举

    基于 DeepSeek-TUI 的 ApprovalRequirement 设计：
    - Auto: 自动审批（YOLO/Agent 模式自动批准，Plan 模式需确认）
    - Suggest: 建议审批（Plan 模式建议确认，YOLO 模式自动）
    - Required: 强制审批（始终需要显式确认）

    与 PermissionDecision 的关系：
    - Auto → PermissionDecision.Allow (YOLO 模式)
    - Auto → PermissionDecision.Ask (Plan 模式)
    - Suggest → PermissionDecision.Ask (Plan 模式)
    - Suggest → PermissionDecision.Allow (YOLO 模式)
    - Required → PermissionDecision.Ask (所有模式)

    用途：
    - 工具声明自己的审批需求
    - 运行时根据信任模式决定最终权限
    """

    Auto = "auto"
    Suggest = "suggest"
    Required = "required"


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

# === Wiki 知识落地 P3: 能力映射 ===

# ToolCapability 默认审批需求映射
CAPABILITY_APPROVAL_MAP: dict[ToolCapability, ApprovalRequirement] = {
    ToolCapability.ReadOnly: ApprovalRequirement.Auto,
    ToolCapability.WritesFiles: ApprovalRequirement.Required,
    ToolCapability.ExecutesCode: ApprovalRequirement.Required,
    ToolCapability.Network: ApprovalRequirement.Suggest,
    ToolCapability.Sandboxable: ApprovalRequirement.Auto,  # 可沙箱化本身不增加审批需求
    ToolCapability.RequiresApproval: ApprovalRequirement.Required,  # 强制覆盖
}

# 需要沙箱隔离的能力
SANDBOX_REQUIRED_CAPABILITIES: set[ToolCapability] = {
    ToolCapability.ExecutesCode,
    ToolCapability.Sandboxable,
}

# 只读能力集合（用于判断并发安全）
READ_ONLY_CAPABILITIES: set[ToolCapability] = {
    ToolCapability.ReadOnly,
}


__all__ = [
    "CAPABILITY_APPROVAL_MAP",
    "CONCURRENCY_SAFE_KINDS",
    "MUTATOR_KINDS",
    "READ_ONLY_CAPABILITIES",
    "SANDBOX_REQUIRED_CAPABILITIES",
    "ApprovalRequirement",
    "PermissionDecision",
    # Wiki 知识落地 P3 (DeepSeek-TUI)
    "ToolCapability",
    # Wiki 知识落地 (Qwen-Code)
    "ToolKind",
]