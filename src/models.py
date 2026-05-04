"""
数据模型与配置加载模块

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

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

logger = logging.getLogger("seed_agent.config")

# 配置迁移版本号
CONFIG_VERSION = 3  # v3: 新增 paths 段


def get_config_path() -> Path:
    """配置文件定位（优先级）

    优先级：
    1. SEED_HOME 环境变量 → $SEED_HOME/config.json
    2. 默认位置 ~/.seed/config.json

    Returns:
        Path: 配置文件路径
    """
    # 1. SEED_HOME 环境变量
    seed_home = os.getenv("SEED_HOME")
    if seed_home:
        path = Path(seed_home).expanduser().resolve()
        return path / "config.json"

    # 2. 默认 ~/.seed
    return Path.home() / ".seed" / "config.json"


class PathsConfig(BaseModel):
    """路径配置

    支持环境变量 SEED_HOME 定位配置文件，
    所有子路径基于 seedBaseDir 自动计算。

    字段说明：
    - seedBaseDir: 主工作目录，默认 ~/.seed
    - projectRoot: 项目根目录，null 时自动检测
    - wikiDir: Wiki 目录，可选
    - allowedDirs: 允许访问的目录列表
    """

    model_config = ConfigDict(extra="ignore")

    # 用户可配置的路径
    seedBaseDir: str = "~/.seed"
    projectRoot: str | None = None
    wikiDir: str | None = None
    allowedDirs: list[str] = []

    @field_validator("seedBaseDir", "projectRoot", "wikiDir", mode="before")
    @classmethod
    def expand_path(cls, v: str | None) -> str | None:
        """展开路径中的 ~ 和环境变量"""
        if v is None:
            return v
        return os.path.expanduser(os.path.expandvars(v))

    @field_validator("allowedDirs", mode="before")
    @classmethod
    def expand_dirs(cls, v: list[str] | None) -> list[str]:
        """展开目录列表中的 ~ 和环境变量"""
        if v is None:
            return []
        return [os.path.expanduser(os.path.expandvars(p)) for p in v]

    # ========== 子路径属性（自动计算）==========

    @property
    def seed_base(self) -> Path:
        """主工作目录"""
        return Path(self.seedBaseDir).resolve()

    @property
    def memory_dir(self) -> Path:
        """记忆存储目录"""
        return self.seed_base / "memory"

    @property
    def sandbox_dir(self) -> Path:
        """沙盒目录"""
        return self.seed_base / "sandbox"

    @property
    def tasks_dir(self) -> Path:
        """任务存储目录"""
        return self.seed_base / "tasks"

    @property
    def cache_dir(self) -> Path:
        """缓存目录"""
        return self.seed_base / "cache"

    @property
    def logs_dir(self) -> Path:
        """日志目录"""
        return self.seed_base / "logs"

    @property
    def vault_dir(self) -> Path:
        """凭证存储目录"""
        return self.seed_base / "vault"

    @property
    def ralph_dir(self) -> Path:
        """Ralph Loop 状态目录"""
        return self.seed_base / "ralph"

    # ========== 数据库路径 ==========

    @property
    def sessions_db(self) -> Path:
        """Session 数据库"""
        return self.memory_dir / "raw" / "sessions.db"

    @property
    def archives_db(self) -> Path:
        """归档数据库"""
        return self.memory_dir / "archives.db"

    @property
    def rate_limit_db(self) -> Path:
        """限流状态数据库"""
        return self.seed_base / "rate_limit.db"

    @property
    def user_modeling_db(self) -> Path:
        """用户建模数据库"""
        return self.seed_base / "user_modeling" / "profiles.db"

    @property
    def events_dir(self) -> Path:
        """事件流存储目录"""
        return self.memory_dir / "events"

    # ========== 外部路径 ==========

    @property
    def project_root(self) -> Path:
        """项目根目录"""
        if self.projectRoot:
            return Path(self.projectRoot).resolve()
        # 自动检测：从 models.py 所在目录向上查找
        return Path(__file__).parent.parent.resolve()

    @property
    def wiki_dir(self) -> Path | None:
        """Wiki 目录"""
        if self.wikiDir:
            return Path(self.wikiDir).resolve()
        return None

    @property
    def allowed_dirs_resolved(self) -> list[Path]:
        """允许访问的目录列表（解析后）"""
        dirs = [Path(p).resolve() for p in self.allowedDirs]
        # 自动添加核心目录
        core_dirs = [
            self.seed_base,
            self.project_root,
        ]
        for d in core_dirs:
            if d not in dirs:
                dirs.append(d)
        return dirs


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

    paths: PathsConfig = PathsConfig()  # 新增路径配置
    models: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    queue: QueueConfigModel | None = None
    timeout: TimeoutConfigModel | None = None
    version: int | None = None


def _migrate_to_v3(data: dict) -> dict:
    """迁移配置到 v3 格式

    迁移规则：
    1. v1 → v2: models.providers -> models, agents.defaults.model -> agents.defaults.defaults.primary
    2. v2 → v3: 添加默认 paths 段

    Args:
        data: 原始配置数据

    Returns:
        迁移后的配置数据
    """
    version = data.get("version", 1)

    # 已是 v3，无需迁移
    if version >= 3:
        return data

    # === v1 → v2 迁移 ===
    if version < 2:
        # 1. models.providers -> models
        if "models" in data and isinstance(data["models"], dict):
            models_section = data["models"]
            if "providers" in models_section:
                data["models"] = models_section["providers"]
                logger.debug("Migrated: models.providers -> models")

        # 2. agents.defaults.model -> agents.defaults.defaults.primary
        if "agents" in data and isinstance(data["agents"], dict):
            agents_section = data["agents"]
            defaults = agents_section.get("defaults")

            if isinstance(defaults, dict):
                # 旧格式: {"defaults": {"model": "..."}}
                if "model" in defaults and "defaults" not in defaults:
                    agents_section["defaults"] = {
                        "defaults": {"primary": defaults["model"]}
                    }
                    logger.debug(
                        "Migrated: agents.defaults.model -> agents.defaults.defaults.primary"
                    )

                # 半迁移格式: {"defaults": {"primary": "..."}}
                elif "primary" in defaults and "defaults" not in defaults:
                    agents_section["defaults"] = {
                        "defaults": {"primary": defaults["primary"]}
                    }
                    logger.debug("Migrated: agents.defaults -> agents.defaults.defaults")

        data["version"] = 2

    # === v2 → v3 迁移 ===
    if data.get("version", 1) < 3:
        # 添加默认 paths 段
        if "paths" not in data:
            data["paths"] = {
                "seedBaseDir": "~/.seed",
                "projectRoot": None,
                "wikiDir": None,
                "allowedDirs": []
            }
            logger.debug("Migrated: added default paths section")

        data["version"] = 3

    logger.info(f"Config migrated to version {data['version']}")
    return data


def load_config(config_path: str | None = None) -> FullConfig:
    """加载并解析配置文件，支持旧版格式自动迁移

    Args:
        config_path: 配置文件路径，默认通过 get_config_path() 获取

    Returns:
        FullConfig: 验证后的完整配置

    Raises:
        ValueError: 配置文件不存在或格式错误
    """
    if config_path is None:
        config_path = str(get_config_path())

    # 读取配置文件
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(
            f"Configuration file not found: {config_path}\n"
            f"Please create the file or set SEED_HOME environment variable."
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {config_path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_path}: {e}")

    # 执行配置迁移
    data = _migrate_to_v3(data)

    # 验证并构建配置对象
    try:
        return FullConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Config validation failed: {e}")