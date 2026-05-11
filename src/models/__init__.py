"""数据模型与配置加载模块

负责:
1. Pydantic 数据模型定义 (配置验证、类型安全)
2. 配置文件加载与解析 (config.json → FullConfig)
3. 路径配置管理 (环境变量 SEED_HOME、动态路径计算)
4. 提供商配置管理 (多 API Key、路由策略)
5. 限流参数建模 (RPM、Rolling Window、并发控制)
6. 环境变量注入 (.env 文件加载、配置覆盖)
7. 配置迁移（旧版格式自动转换）
8. 模型别名映射 (别名到规范 ID、大小写保持) - P6 新增

核心模型:
- PathsConfig: 路径配置（支持 SEED_HOME）
- FullConfig: 完整系统配置
- ProviderConfig: LLM 提供商配置
- ModelConfig: 模型参数 (temperature, max_tokens 等)
- RateLimitConfig: 限流策略

Wiki 知识落地 P6 (DeepSeek-TUI ModelAliasRegistry):
- ModelAliasRegistry: 模型别名映射注册表
- ResolvedModel: 解析后的模型信息
- ProviderKind: 提供商类型枚举
- 别名映射: 支持 deepseek-chat → deepseek-v4-flash 等别名
- 大小写保持: 解析后保持用户指定的大小写

版本: v2.2 (Wiki 知识落地 P6 版)
"""

# 从子模块导入所有内容
from src.models._alias_registry import (
    ModelAliasRegistry,
    ModelInfo,
    ProviderKind,
    ResolvedModel,
    get_global_registry,
    reset_global_registry,
)
from src.models._config_loader import (
    CONFIG_VERSION,
    _migrate_to_v3,
    get_config_path,
    load_config,
)
from src.models._paths_models import PathsConfig
from src.models._provider_models import (
    AgentConfig,
    AgentModelConfig,
    FullConfig,
    ModelConfig,
    ProviderConfig,
    QueueConfigModel,
    RateLimitConfig,
    TimeoutConfigModel,
)

__all__ = [
    # Wiki 知识落地 P6 (DeepSeek-TUI ModelAliasRegistry)
    "ModelAliasRegistry",
    "ModelInfo",
    "ProviderKind",
    "ResolvedModel",
    # 配置加载
    "CONFIG_VERSION",
    "AgentConfig",
    "AgentModelConfig",
    "FullConfig",
    "ModelConfig",
    # 路径模型
    "PathsConfig",
    "ProviderConfig",
    "QueueConfigModel",
    # 提供商模型
    "RateLimitConfig",
    "TimeoutConfigModel",
    "_migrate_to_v3",
    "get_config_path",
    "get_global_registry",
    "load_config",
    "reset_global_registry",
]