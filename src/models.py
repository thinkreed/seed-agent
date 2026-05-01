"""
数据模型与配置加载模块

负责:
1. Pydantic 数据模型定义 (配置验证、类型安全)
2. 配置文件加载与解析 (config.json → FullConfig)
3. 提供商配置管理 (多 API Key、路由策略)
4. 限流参数建模 (RPM、Rolling Window、并发控制)
5. 环境变量注入 (.env 文件加载、配置覆盖)
6. 配置迁移（旧版格式自动转换）

核心模型:
- FullConfig: 完整系统配置
- ProviderConfig: LLM 提供商配置
- ModelConfig: 模型参数 (temperature, max_tokens 等)
- RateLimitConfig: 限流策略
"""

import json
import logging
import os

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

logger = logging.getLogger("seed_agent.config")

DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".seed", "config.json")

# 配置迁移版本号
CONFIG_VERSION = 2  # v1: 原始格式, v2: 新嵌套格式


class RateLimitConfig(BaseModel):
    """限流配置

    支持两种限流模式:
    - rolling_window: 滚动窗口（如百炼 5小时6000次）
    - rpm: 固定 RPM（如 OpenAI 标准限流）
    """
    model_config = ConfigDict(extra='ignore')

    # 滚动窗口模式
    rollingWindowRequests: int | None = None  # 窗口内最大请求
    rollingWindowDuration: int | None = None  # 窗口时长（秒）

    # 固定 RPM 模式
    rpm: int | None = None  # 每分钟请求限制

    # 突发容量
    burstCapacity: int = 100

    # 并发控制
    maxConcurrent: int = 3

    # 队列配置
    queueMaxSize: int = 50
    queueBackpressureThreshold: float = 0.8

    def get_effective_rate(self) -> float:
        """计算有效速率（requests/sec）"""
        if self.rpm is not None:
            return self.rpm / 60.0

        if self.rollingWindowRequests is not None and self.rollingWindowDuration is not None:
            return self.rollingWindowRequests / self.rollingWindowDuration

        # 默认百炼规格: 6000/18000 = 0.33 req/sec
        return 6000 / 18000

    def get_window_limit(self) -> int:
        """获取窗口请求上限"""
        if self.rollingWindowRequests is not None:
            return self.rollingWindowRequests
        # 基于 RPM 推算 5 小时窗口
        if self.rpm is not None:
            return self.rpm * 300  # 5 hours = 300 minutes
        return 6000

    def get_window_duration(self) -> float:
        """获取窗口时长（秒）"""
        if self.rollingWindowDuration is not None:
            return float(self.rollingWindowDuration)
        return 18000.0  # 默认 5 小时


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str
    name: str
    contextWindow: int = 100000
    maxTokens: int = 4096
    compat: dict | None = None


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    baseUrl: str
    apiKey: str
    api: str = "openai-completions"
    models: list[ModelConfig]
    rateLimit: RateLimitConfig | None = None

    @field_validator('apiKey', 'baseUrl')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if v else v


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    primary: str


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    defaults: AgentModelConfig


class QueueConfigModel(BaseModel):
    """队列配置（TurnTicket 模式）"""
    model_config = ConfigDict(extra='ignore')

    # CRITICAL 队列配置
    critical_max_size: int = 10
    critical_backpressure_threshold: float = 0.9
    critical_dispatch_rate: float = 10.0
    critical_target_wait_time: float = 5.0

    # 普通队列配置（HIGH/NORMAL/LOW 共享）
    normal_max_size: int = 50
    normal_backpressure_threshold: float = 0.8
    normal_dispatch_rate: float = 0.33
    normal_target_wait_time: float = 30.0

    # 自动调整
    auto_adjust_enabled: bool = True
    adjust_interval: float = 60.0


class TimeoutConfigModel(BaseModel):
    """等待超时配置（动态调整）"""
    model_config = ConfigDict(extra='ignore')

    # 基础超时（秒）
    critical_base_timeout: float = 30.0
    high_base_timeout: float = 60.0
    normal_base_timeout: float = 120.0
    low_base_timeout: float = 300.0

    # 动态调整参数
    auto_adjust_enabled: bool = True
    load_factor_threshold: float = 0.7
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0


class FullConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    models: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    queue: QueueConfigModel | None = None
    timeout: TimeoutConfigModel | None = None
    version: int | None = None  # 配置版本号（可选）


def _migrate_v1_to_v2(data: dict) -> dict:
    """迁移 v1 配置格式到 v2

    迁移规则:
    1. models.providers -> models
    2. agents.defaults.model -> agents.defaults.defaults.primary

    Args:
        data: 原始配置数据

    Returns:
        迁移后的配置数据
    """
    # 检查是否已迁移
    if data.get('version', 1) >= CONFIG_VERSION:
        return data

    migrated = False

    # 1. models.providers -> models
    if 'models' in data and isinstance(data['models'], dict):
        models_section = data['models']
        if 'providers' in models_section:
            data['models'] = models_section['providers']
            migrated = True
            logger.debug("Migrated: models.providers -> models")

    # 2. agents.defaults.model -> agents.defaults.defaults.primary
    if 'agents' in data and isinstance(data['agents'], dict):
        agents_section = data['agents']
        defaults = agents_section.get('defaults')
        
        if isinstance(defaults, dict):
            # 旧格式: {"defaults": {"model": "..."}}
            if 'model' in defaults and 'defaults' not in defaults:
                agents_section['defaults'] = {
                    'defaults': {'primary': defaults['model']}
                }
                migrated = True
                logger.debug("Migrated: agents.defaults.model -> agents.defaults.defaults.primary")
            
            # 半迁移格式: {"defaults": {"primary": "..."}}
            elif 'primary' in defaults and 'defaults' not in defaults:
                agents_section['defaults'] = {
                    'defaults': {'primary': defaults['primary']}
                }
                migrated = True
                logger.debug("Migrated: agents.defaults -> agents.defaults.defaults")

    # 标记迁移版本
    if migrated:
        data['version'] = CONFIG_VERSION
        logger.info(f"Config migrated to version {CONFIG_VERSION}")

    return data


def load_config(config_path: str | None = None) -> FullConfig:
    """加载并解析配置文件，支持旧版 JSON 结构自动迁移

    Args:
        config_path: 配置文件路径，默认为 ~/.seed/config.json

    Returns:
        FullConfig: 验证后的完整配置

    Raises:
        ValueError: 配置文件不存在或格式错误
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    # 读取配置文件
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(
            f"Configuration file not found: {config_path}\n"
            f"Please create the file or specify a valid config path."
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {config_path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_path}: {e}")

    # 执行配置迁移
    data = _migrate_v1_to_v2(data)

    # 验证并构建配置对象
    try:
        return FullConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Config validation failed: {e}")