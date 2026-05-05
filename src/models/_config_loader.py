"""配置加载器

包含配置文件加载和迁移逻辑。

内容:
- get_config_path: 配置文件定位
- _migrate_to_v3: 配置迁移
- load_config: 配置加载
"""

import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from src.models._paths_models import PathsConfig
from src.models._provider_models import FullConfig

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
                    logger.debug(
                        "Migrated: agents.defaults -> agents.defaults.defaults"
                    )

        data["version"] = 2

    # === v2 → v3 迁移 ===
    if data.get("version", 1) < 3:
        # 添加默认 paths 段
        if "paths" not in data:
            data["paths"] = {
                "seedBaseDir": "~/.seed",
                "projectRoot": None,
                "wikiDir": None,
                "allowedDirs": [],
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
        ) from None
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {config_path}: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_path}: {e}") from e

    # 执行配置迁移
    data = _migrate_to_v3(data)

    # 确保 paths 段存在
    if "paths" not in data:
        data["paths"] = PathsConfig().model_dump()

    # 验证并构建配置对象
    try:
        return FullConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Config validation failed: {e}") from e