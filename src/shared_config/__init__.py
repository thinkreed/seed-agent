"""共享配置模块 - 统一路径管理

改动：
1. 移除 SEED_DIR 硕编码
2. 从 PathsConfig 动态读取路径
3. 提供全局 PathsConfig 访问接口
4. 其他配置类保持不变

统一管理:
- Memory Graph 参数
- Subagent 超时配置
- 路径验证配置（动态）
- 代码执行安全规则
"""

# 从子模块导入所有内容（向后兼容）
from src.shared_config._config_dataclasses import (
    AutonomousConfig,
    CodeExecutionSecurityConfig,
    MemoryGraphConfig,
    PathValidationConfig,
    QueueConfig,
    RalphLoopConfig,
    SubagentTimeoutConfig,
    VisionConfig,
    get_autonomous_config,
    get_code_execution_security_config,
    get_memory_graph_config,
    get_path_validation_config,
    get_primary_model,
    get_queue_config,
    get_ralph_loop_config,
    get_subagent_timeout_config,
    get_vision_config,
)
from src.shared_config._path_management import (
    get_allowed_dirs,
    get_cache_dir,
    get_cache_dir_with_fallback,
    get_logs_dir,
    get_memory_dir,
    get_memory_dir_with_fallback,
    get_paths_config,
    get_project_root,
    get_ralph_dir,
    get_ralph_dir_with_fallback,
    get_sandbox_dir,
    get_sandbox_dir_with_fallback,
    get_seed_dir,
    get_seed_dir_with_fallback,
    get_tasks_dir,
    get_tasks_dir_with_fallback,
    get_vault_dir,
    get_wiki_dir,
    init_paths_config,
)

# 导出所有公共接口
__all__ = [
    "AutonomousConfig",
    "CodeExecutionSecurityConfig",
    # 配置数据类
    "MemoryGraphConfig",
    "PathValidationConfig",
    "QueueConfig",
    "RalphLoopConfig",
    "SubagentTimeoutConfig",
    "VisionConfig",
    "get_allowed_dirs",
    "get_autonomous_config",
    "get_cache_dir",
    "get_cache_dir_with_fallback",
    "get_code_execution_security_config",
    "get_logs_dir",
    "get_memory_dir",
    "get_memory_dir_with_fallback",
    # 配置获取函数
    "get_memory_graph_config",
    "get_path_validation_config",
    "get_paths_config",
    "get_primary_model",
    "get_project_root",
    "get_queue_config",
    "get_ralph_dir",
    "get_ralph_dir_with_fallback",
    "get_ralph_loop_config",
    "get_sandbox_dir",
    "get_sandbox_dir_with_fallback",
    "get_seed_dir",
    "get_seed_dir_with_fallback",
    "get_subagent_timeout_config",
    "get_tasks_dir",
    "get_tasks_dir_with_fallback",
    "get_vault_dir",
    "get_vision_config",
    "get_wiki_dir",
    # 路径管理
    "init_paths_config",
]