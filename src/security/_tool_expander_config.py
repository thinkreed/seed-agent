"""渐进式工具扩展器配置"""

from src.security._tool_expander_types import ToolTier, ToolTierConfig

TOOL_TIER_CONFIGS: dict[ToolTier, ToolTierConfig] = {
    ToolTier.TIER_0_MINIMAL: ToolTierConfig(
        description="最小工具集 - 只读操作",
        tools={"file_read", "list_directory", "ask_user", "search_history", "read_memory_index",
               "search_memory", "load_skill", "git_status", "git_diff", "list_subagents",
               "check_ralph_status", "list_scheduled_tasks"},
        trigger_conditions=["session_start", "initial_context"],
    ),
    ToolTier.TIER_1_BASIC: ToolTierConfig(
        description="基础工具集 - 常用操作",
        tools={"file_read", "list_directory", "ask_user", "search_history", "read_memory_index",
               "search_memory", "load_skill", "git_status", "git_diff", "list_subagents",
               "check_ralph_status", "list_scheduled_tasks", "find_file", "grep_search",
               "run_diagnosis", "wait_for_subagent", "aggregate_subagent_results"},
        trigger_conditions=["first_user_request", "exploration_task"],
    ),
    ToolTier.TIER_2_EXTENDED: ToolTierConfig(
        description="扩展工具集 - 写入操作",
        tools={"file_read", "list_directory", "ask_user", "search_history", "read_memory_index",
               "search_memory", "load_skill", "git_status", "git_diff", "list_subagents",
               "check_ralph_status", "list_scheduled_tasks", "find_file", "grep_search",
               "run_diagnosis", "wait_for_subagent", "aggregate_subagent_results",
               "file_write", "file_edit", "create_directory", "write_memory", "git_commit",
               "spawn_subagent", "create_scheduled_task", "run_test", "run_python_script"},
        trigger_conditions=["implementation_task", "refactoring_task", "iteration_threshold"],
    ),
    ToolTier.TIER_3_FULL: ToolTierConfig(
        description="完整工具集 - 高风险操作",
        tools={"file_read", "list_directory", "ask_user", "search_history", "read_memory_index",
               "search_memory", "load_skill", "git_status", "git_diff", "list_subagents",
               "check_ralph_status", "list_scheduled_tasks", "find_file", "grep_search",
               "run_diagnosis", "wait_for_subagent", "aggregate_subagent_results",
               "file_write", "file_edit", "create_directory", "write_memory", "git_commit",
               "spawn_subagent", "create_scheduled_task", "run_test", "run_python_script",
               "code_as_policy", "run_shell_command", "delete_file", "install_package",
               "git_push", "kill_subagent", "remove_scheduled_task", "mark_ralph_complete", "start_ralph_loop"},
        trigger_conditions=["trusted_user", "complex_task", "admin_request"],
    ),
}

TASK_TYPE_TIER_MAP: dict[str, ToolTier] = {
    "exploration": ToolTier.TIER_1_BASIC, "review": ToolTier.TIER_1_BASIC,
    "analysis": ToolTier.TIER_1_BASIC, "search": ToolTier.TIER_1_BASIC,
    "implementation": ToolTier.TIER_2_EXTENDED, "refactoring": ToolTier.TIER_2_EXTENDED,
    "fix": ToolTier.TIER_2_EXTENDED, "debug": ToolTier.TIER_2_EXTENDED,
    "deployment": ToolTier.TIER_3_FULL, "system": ToolTier.TIER_3_FULL, "admin": ToolTier.TIER_3_FULL,
}

USER_PERMISSION_TIER_LIMITS: dict[str, ToolTier] = {
    "admin": ToolTier.TIER_3_FULL, "trusted": ToolTier.TIER_3_FULL,
    "normal": ToolTier.TIER_2_EXTENDED, "guest": ToolTier.TIER_1_BASIC,
    "restricted": ToolTier.TIER_0_MINIMAL,
}

TIER_ORDER: list[ToolTier] = [
    ToolTier.TIER_0_MINIMAL, ToolTier.TIER_1_BASIC, ToolTier.TIER_2_EXTENDED, ToolTier.TIER_3_FULL,
]