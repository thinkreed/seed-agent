"""提供商配置模型

包含 Provider、Agent、Queue 等相关的 Pydantic 模型定义。

内容:
- RateLimitConfig: 限流配置
- ModelConfig: 模型参数
- ProviderConfig: 提供商配置
- AgentModelConfig/AgentConfig: 智能体配置
- QueueConfigModel: 队列配置
- TimeoutConfigModel: 超时配置
- FullConfig: 完整配置
"""

from pydantic import BaseModel, ConfigDict, field_validator


class RateLimitConfig(BaseModel):
    """限流配置

    支持两种限流模式:
    - rolling_window: 滚动窗口（如百炼 5小时6000次）
    - rpm: 固定 RPM（如 OpenAI 标准限流）
    """

    model_config = ConfigDict(extra="ignore")

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

        if (
            self.rollingWindowRequests is not None
            and self.rollingWindowDuration is not None
        ):
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
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    contextWindow: int = 100000
    maxTokens: int = 4096
    compat: dict | None = None


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    baseUrl: str
    apiKey: str
    api: str = "openai-completions"
    models: list[ModelConfig]
    rateLimit: RateLimitConfig | None = None

    @field_validator("apiKey", "baseUrl")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if v else v


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primary: str


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    defaults: AgentModelConfig


class QueueConfigModel(BaseModel):
    """队列配置（TurnTicket 模式）"""

    model_config = ConfigDict(extra="ignore")

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

    model_config = ConfigDict(extra="ignore")

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
    """完整配置"""
    model_config = ConfigDict(extra="ignore")

    paths: "PathsConfig"  # 路径配置
    models: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    queue: QueueConfigModel | None = None
    timeout: TimeoutConfigModel | None = None
    version: int | None = None


# 延迟导入解决循环依赖
def _update_full_config_forward_ref():
    """更新 FullConfig 的前向引用"""
    from src.models._paths_models import PathsConfig
    FullConfig.model_rebuild()


# 在模块加载时更新
_update_full_config_forward_ref()