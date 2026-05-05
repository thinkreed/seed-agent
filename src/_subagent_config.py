"""
Subagent 配置模块

包含权限集、系统提示、超时配置等
"""

# 权限集定义
PERMISSION_SETS: dict[str, set[str]] = {
    "read_only": {
        "file_read",
        "search_history",
        "ask_user",
    },
    "review": {
        "file_read",
        "code_as_policy",
        "search_history",
        "ask_user",
    },
    "implement": {
        "file_read",
        "file_write",
        "file_edit",
        "code_as_policy",
        "write_memory",
        "read_memory_index",
        "search_memory",
        "search_history",
        "ask_user",
        "run_diagnosis",
    },
    "plan": {
        "file_read",
        "write_memory",
        "read_memory_index",
        "search_memory",
        "search_history",
        "ask_user",
    },
}

# Subagent 类型对应的默认权限集
# 使用字符串键以支持跨模块导入的枚举比较
SUBAGENT_TYPE_PERMISSIONS: dict[str, str] = {
    "explore": "read_only",
    "review": "review",
    "implement": "implement",
    "plan": "plan",
}

# Subagent 类型对应的 system prompt 模板
# 使用字符串键以支持跨模块导入的枚举比较
SUBAGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "explore": """你是一个探索型子代理 (Explore Subagent)。

你的职责是：
- 搜索和分析代码文件
- 理解项目结构和代码逻辑
- 收集信息并汇报发现

限制：
- 你只能读取文件，不能修改任何内容
- 完成后提供简洁的发现摘要
- 不要输出冗长的原始文件内容，只输出关键发现""",
    "review": """你是一个审查型子代理 (Review Subagent)。

你的职责是：
- 审查代码质量和安全性
- 运行测试验证功能
- 检查代码规范和最佳实践

限制：
- 你只能读取文件和执行代码
- 不能修改任何文件
- 完成后提供结构化的审查报告""",
    "implement": """你是一个实现型子代理 (Implement Subagent)。

你的职责是：
- 实现功能代码
- 修复 bug
- 重构代码

能力：
- 完整的文件读写权限
- 代码执行能力
- 记忆系统访问

完成后提供简洁的实现总结。""",
    "plan": """你是一个规划型子代理 (Plan Subagent)。

你的职责是：
- 分析任务需求
- 制定执行计划
- 记录关键决策到记忆系统

限制：
- 你只能读取文件和写入记忆
- 不能修改代码文件
- 完成后提供结构化的执行计划""",
}

# 使用共享配置模块
try:
    from src.shared_config import get_subagent_timeout_config

    _timeout_config = get_subagent_timeout_config()
    _default_timeouts = {
        "explore": _timeout_config.explore,
        "review": _timeout_config.review,
        "implement": _timeout_config.implement,
        "plan": _timeout_config.plan,
    }
    MAX_SUBAGENT_ITERATIONS = _timeout_config.max_iterations
except ImportError:
    # Fallback: 使用默认值
    _default_timeouts = {
        "explore": 180,
        "review": 600,
        "implement": 900,
        "plan": 300,
    }
    MAX_SUBAGENT_ITERATIONS = 15

# 导出为模块级常量
DEFAULT_TIMEOUTS: dict[str, int] = _default_timeouts