"""
数据模型与配置加载模块

负责:
1. Pydantic 数据模型定义 (配置验证、类型安全)
2. 配置文件加载与解析 (config.json → FullConfig)
3. 提供商配置管理 (多 API Key、路由策略)
4. 限流参数建模 (RPM、Rolling Window、并发控制)
5. 环境变量注入 (.env 文件加载、配置覆盖)

核心模型:
- FullConfig: 完整系统配置
- ProviderConfig: LLM 提供商配置
- ModelConfig: 模型参数 (temperature, max_tokens 等)
- RateLimitConfig: 限流策略
"""

from pydantic import BaseModel, ConfigDict, field_validator, ValidationError
# 类型注解使用内置类型，不再需要从 typing 导入
import json
import os

DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".seed", "config.json")


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

def load_config(config_path: str = None) -> FullConfig:
    """加载并解析配置文件，支持旧版 JSON 结构自动迁移
    
    Args:
        config_path: 配置文件路径，默认为 ~/.seed/config.json
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(
            f"Configuration file not found: {config_path}\n"
            f"Please create the file or specify a valid config path."
        )
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_path}: {e}")

    # 迁移逻辑: 适配旧版 JSON 结构
    # 1. 处理 models.providers -> models
    if 'models' in data and isinstance(data['models'], dict) and 'providers' in data['models']:
        data['models'] = data['models']['providers']

    # 2. 处理 agents.defaults.model -> agents.defaults.defaults
    #    幂等迁移：已迁移过的配置不会被重复处理
    if 'agents' in data and isinstance(data['agents'], dict):
        agent_section = data['agents']
        if 'defaults' in agent_section and isinstance(agent_section['defaults'], dict):
            defaults = agent_section['defaults']
            # 旧格式: {"defaults": {"model": "..."}}
            if 'model' in defaults:
                agent_section['defaults'] = {
                    'defaults': {'primary': defaults['model']}
                }
            # 半迁移格式: {"defaults": {"primary": "..."}} → 补全嵌套
            elif 'primary' in defaults and 'defaults' not in defaults:
                agent_section['defaults'] = {
                    'defaults': {'primary': defaults['primary']}
                }
            # 已迁移格式: {"defaults": {"defaults": {"primary": "..."}}} → 无需处理

    try:
        return FullConfig(**data)
    except ValidationError:
        raise
