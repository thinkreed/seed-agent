"""数据模型与配置加载模块

负责:
1. Pydantic 数据模型定义 (配置验证、类型安全)
2. 配置文件加载与解析 (config.json → FullConfig)
3. 路径配置管理 (环境变量 SEED_HOME、动态路径计算)
4. 提供商配置管理 (多 API Key、路由策略)
5. 限流参数建模 (RPM、Rolling Window、并发控制)
6. 环境变量注入 (.env 文件加载、配置覆盖)
7. 配置迁移（旧版格式自动转换）

核心模型:
- PathsConfig: 路径配置（新增，支持 SEED_HOME）
- FullConfig: 完整系统配置
- ProviderConfig: LLM 提供商配置
- ModelConfig: 模型参数 (temperature, max_tokens 等)
- RateLimitConfig: 限流策略
"""

# 从子模块导入所有内容
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
    # 路径模型
    "PathsConfig",
    # 提供商模型
    "RateLimitConfig",
    "ModelConfig",
    "ProviderConfig",
    "AgentModelConfig",
    "AgentConfig",
    "QueueConfigModel",
    "TimeoutConfigModel",
    "FullConfig",
    # 配置加载
    "CONFIG_VERSION",
    "get_config_path",
    "_migrate_to_v3",
    "load_config",
]