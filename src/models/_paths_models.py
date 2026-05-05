"""路径配置模型

包含路径相关的 Pydantic 模型定义。

内容:
- PathsConfig: 路径配置（支持 SEED_HOME）
- 子路径属性计算
"""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator


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
        return Path(__file__).parent.parent.parent.resolve()

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