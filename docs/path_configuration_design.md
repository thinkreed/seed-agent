# Seed Agent 路径配置优化方案

> **状态**: ✅ 已落地实施 (2026-05-04)
> **方案类型**: 环境变量驱动 + 配置文件定义
> **设计目标**: 统一管理所有路径，消除硬编码，支持多环境切换
> **生成日期**: 2026-05-04

---

## 实施摘要

本方案已完成全面落地实施，主要改动：

1. **新增 `PathsConfig` 模型** (`src/models.py`)：环境变量 SEED_HOME 支持、动态路径计算
2. **重构 `shared_config.py`**：移除硬编码 `SEED_DIR`，改为动态读取
3. **全局路径迁移**：15+ 文件移除硬编码 `Path.home() / ".seed"`
4. **配置自动迁移**：v2 → v3 添加默认 `paths` 段

### 使用示例

```bash
# 默认 ~/.seed/config.json
python main.py

# 自定义配置位置
SEED_HOME=/data/seed python main.py
```

```python
from src.shared_config import get_paths_config, get_seed_dir

# 获取配置
paths = get_paths_config()

# 使用路径
memory_file = paths.memory_dir / "notes.md"
db_path = paths.sessions_db
```

---

## 一、原状分析（已解决）

### 1.1 原问题清单（已解决）

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| **路径硬编码** | ✅ 已解决 | 所有路径从 PathsConfig 动态获取 |
| **配置路径固定** | ✅ 已解决 | 支持 SEED_HOME 环境变量 |
| **子路径分散** | ✅ 已解决 | PathsConfig 集中管理所有子路径 |
| **allowedDirs 硬编码** | ✅ 已解决 | 配置文件 paths.allowedDirs 字段 |

### 1.2 当前路径使用分布

```
~/.seed/ (SEED_DIR - shared_config.py:18)
├── config.json          ← main.py 硬编码定位
├── memory/
│   ├── notes.md         ← memory_tools.py
│   ├── skills/          ← skill_loader.py
│   ├── knowledge/       ← memory_manager.py
│   ├── raw/sessions.db  ← session_db.py
│   └── archives.db      ← long_term_archive.py
├── sandbox/             ← sandbox.py
├── tasks/               ← scheduler.py
├── cache/               ← skill_cache.py
├── ralph/               ← ralph_state.py
├── logs/                ← main.py
├── rate_limit.db        ← rate_limit_db.py
└── vault/               ← credential_vault.py

硬编码外部路径:
- E:/projects/wiki       ← shared_config.py:122
- 项目根目录              ← shared_config.py:109
```

### 1.3 需迁移文件清单

| 文件 | 行号 | 当前代码 | 迁移策略 |
|------|------|----------|----------|
| `src/shared_config.py` | 18 | `SEED_DIR = Path.home() / ".seed"` | 从配置读取 |
| `src/shared_config.py` | 122 | `Path("E:/projects/wiki")` | 配置文件定义 |
| `src/models.py` | 27 | `DEFAULT_CONFIG_PATH = Path.home() / ".seed" / "config.json"` | 动态计算 |
| `main.py` | 21 | `LOG_DIR = Path.home() / ".seed" / "logs"` | 从配置读取 |
| `main.py` | 425 | `config_path = os.path.join(..., ".seed", "config.json")` | 使用 SEED_HOME |
| `src/security/credential_vault.py` | 34 | `DEFAULT_VAULT_PATH = Path.home() / ".seed" / "vault"` | 从配置读取 |
| `src/tools/long_term_archive.py` | 40 | `ARCHIVE_DB_PATH = Path.home() / ".seed" / ...` | 从配置读取 |
| `src/tools/skill_cache.py` | 18 | `CACHE_DIR = Path.home() / ".seed" / "cache"` | 从配置读取 |
| `src/tools/user_modeling.py` | 30 | `USER_MODELING_DB_PATH = Path.home() / ".seed" / ...` | 从配置读取 |
| `src/tools/vision_api.py` | 24 | `DEFAULT_CONFIG_PATH = Path.home() / ".seed" / ...` | 从配置读取 |
| `src/rate_limit_db.py` | 46 | `DB_PATH = Path.home() / ".seed" / "rate_limit.db"` | 从配置读取 |

---

## 二、设计方案

### 2.1 核心架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    环境变量 + 配置文件双层架构                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  配置定位优先级 (从高到低):                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 1. SEED_HOME 环境变量                                        │   │
│  │    → $SEED_HOME/config.json                                 │   │
│  │                                                             │   │
│  │ 2. 默认位置 ~/.seed                                          │   │
│  │    → ~/.seed/config.json                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  配置文件定义所有路径:                                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ config.json                                                 │   │
│  │ ├── paths.seedBaseDir      → 主工作目录 (默认 ~/.seed)        │   │
│  │ ├── paths.wikiDir          → Wiki 目录 (替代硬编码)           │   │
│  │ ├── paths.projectRoot      → 项目根目录                       │   │
│  │ ├── paths.allowedDirs      → 允许访问的目录列表               │   │
│  │ └───────────────────────────────────────────────────────    │   │
│  │ 所有子路径基于 seedBaseDir 自动计算:                          │   │
│  │ ├── memory_dir   = seedBaseDir / "memory"                   │   │
│  │ ├── sandbox_dir  = seedBaseDir / "sandbox"                  │   │
│  │ ├── tasks_dir    = seedBaseDir / "tasks"                    │   │
│  │ ├── cache_dir    = seedBaseDir / "cache"                    │   │
│  │ ├── logs_dir     = seedBaseDir / "logs"                     │   │
│  │ ├── vault_dir    = seedBaseDir / "vault"                    │   │
│  │ └─────────────────────────────────────────────────────────  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 配置文件新增 `paths` 段

```json
{
  "version": 3,
  "paths": {
    "seedBaseDir": "~/.seed",
    "projectRoot": null,
    "wikiDir": "E:/projects/wiki",
    "allowedDirs": [
      "~/.seed",
      "~/Documents",
      "E:/projects/wiki"
    ]
  },
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "api": "openai-completions",
      "models": [...]
    }
  },
  "agents": {
    "defaults": {
      "defaults": {
        "primary": "bailian/qwen-coder-plus"
      }
    }
  }
}
```

#### `paths` 段字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `seedBaseDir` | `string` | `~/.seed` | 主工作目录，所有子路径基于此 |
| `projectRoot` | `string \| null` | 运行时计算 | 项目根目录，null 时自动检测 |
| `wikiDir` | `string \| null` | `null` | Wiki 目录，替代硬编码 |
| `allowedDirs` | `string[]` | `[]` | 允许访问的目录列表，用于路径验证 |

#### 子路径自动计算规则

```python
# 所有子路径基于 seedBaseDir 计算，无需单独配置
memory_dir   = seedBaseDir / "memory"
sandbox_dir  = seedBaseDir / "sandbox"
tasks_dir    = seedBaseDir / "tasks"
cache_dir    = seedBaseDir / "cache"
logs_dir     = seedBaseDir / "logs"
vault_dir    = seedBaseDir / "vault"
ralph_dir    = seedBaseDir / "ralph"

# 数据库路径
sessions_db      = seedBaseDir / "memory" / "raw" / "sessions.db"
archives_db      = seedBaseDir / "memory" / "archives.db"
rate_limit_db    = seedBaseDir / "rate_limit.db"
user_modeling_db = seedBaseDir / "user_modeling" / "profiles.db"
```

### 2.3 环境变量设计

| 环境变量 | 用途 | 示例 |
|----------|------|------|
| `SEED_HOME` | 定位配置文件根目录 | `SEED_HOME=/data/seed python main.py` |

**配置文件定位逻辑**:

```python
def get_config_path() -> Path:
    """定位配置文件"""
    # 1. SEED_HOME 环境变量
    seed_home = os.getenv("SEED_HOME")
    if seed_home:
        return Path(seed_home).expanduser().resolve() / "config.json"
    
    # 2. 默认位置 ~/.seed
    return Path.home() / ".seed" / "config.json"
```

### 2.4 platformdirs 使用场景

虽然主工作目录保持 `~/.seed`，但以下场景使用 `platformdirs`:

| 场景 | platformdirs 函数 | 默认路径 |
|------|-------------------|----------|
| **系统缓存** (非 Seed 数据) | `user_cache_path()` | Linux: `~/.cache/SeedAgent` |
| **临时文件** | `user_cache_path()` | macOS: `~/Library/Caches/SeedAgent` |
| **用户配置** (可选) | `user_config_path()` | Windows: `%LOCALAPPDATA%\SeedAgent` |

**示例**: 临时下载文件存储

```python
from platformdirs import user_cache_path

# 临时文件缓存（非核心数据）
TEMP_CACHE = user_cache_path("SeedAgent", appauthor=False) / "downloads"
```

---

## 三、数据模型设计

### 3.1 Pydantic 模型扩展 (`models.py`)

```python
from pathlib import Path
from pydantic import BaseModel, field_validator, ConfigDict
import os

class PathsConfig(BaseModel):
    """路径配置"""
    model_config = ConfigDict(extra="ignore")
    
    # 用户可配置的路径
    seedBaseDir: str = "~/.seed"
    projectRoot: str | None = None
    wikiDir: str | None = None
    allowedDirs: list[str] = []
    
    @field_validator("seedBaseDir", "projectRoot", "wikiDir", "allowedDirs", mode="before")
    @classmethod
    def expand_paths(cls, v: str | list | None) -> str | list | None:
        """展开路径中的 ~ 和环境变量"""
        if v is None:
            return v
        if isinstance(v, str):
            return os.path.expanduser(os.path.expandvars(v))
        if isinstance(v, list):
            return [os.path.expanduser(os.path.expandvars(p)) for p in v]
        return v
    
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
    
    # ========== 外部路径 ==========
    
    @property
    def project_root(self) -> Path:
        """项目根目录"""
        if self.projectRoot:
            return Path(self.projectRoot).resolve()
        # 自动检测：从 shared_config.py 所在目录向上查找
        return Path(__file__).parent.parent.parent.resolve()
    
    @property
    def wiki_dir(self) -> Path | None:
        """Wiki 目录"""
        if self.wikiDir:
            return Path(self.wikiDir).resolve()
        return None
    
    @property
    def allowed_dirs(self) -> list[Path]:
        """允许访问的目录列表"""
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


class FullConfig(BaseModel):
    """完整配置"""
    model_config = ConfigDict(extra="ignore")
    
    paths: PathsConfig = PathsConfig()  # 新增
    models: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    queue: QueueConfigModel | None = None
    timeout: TimeoutConfigModel | None = None
    version: int | None = None
```

### 3.2 配置迁移 (`models.py`)

```python
CONFIG_VERSION = 3  # v3: 新增 paths 段

def _migrate_to_v3(data: dict) -> dict:
    """迁移到 v3 格式：添加默认 paths 段"""
    if data.get("version", 1) >= 3:
        return data
    
    # 添加默认 paths 段
    if "paths" not in data:
        data["paths"] = {
            "seedBaseDir": "~/.seed",
            "projectRoot": None,
            "wikiDir": None,  # 旧用户需手动配置
            "allowedDirs": []
        }
    
    data["version"] = 3
    return data
```

### 3.3 配置加载改造 (`models.py`)

```python
def get_config_path() -> Path:
    """配置文件定位（优先级）"""
    # 1. SEED_HOME 环境变量
    seed_home = os.getenv("SEED_HOME")
    if seed_home:
        path = Path(seed_home).expanduser().resolve()
        return path / "config.json"
    
    # 2. 默认 ~/.seed
    return Path.home() / ".seed" / "config.json"


def load_config(config_path: str | None = None) -> FullConfig:
    """加载配置文件"""
    if config_path is None:
        config_path = str(get_config_path())
    
    # 读取文件
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    
    # 迁移到最新版本
    data = _migrate_to_v3(data)
    
    # 验证并构建
    return FullConfig(**data)
```

---

## 四、shared_config.py 改造

### 4.1 改造方案

```python
"""
共享配置模块 - 统一路径管理

改动:
1. 移除 SEED_DIR 硬编码
2. 从配置文件读取路径
3. 提供全局 PathsConfig 访问接口
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# 全局配置实例（延迟初始化）
_paths_config: Optional["PathsConfig"] = None


def init_paths_config(config: "PathsConfig") -> None:
    """初始化全局路径配置"""
    global _paths_config
    _paths_config = config


def get_paths_config() -> "PathsConfig":
    """获取全局路径配置"""
    if _paths_config is None:
        raise RuntimeError(
            "PathsConfig 未初始化，请先调用 init_paths_config() "
            "或在 AgentLoop 启动后使用"
        )
    return _paths_config


# ========== 便利访问函数 ==========

def get_seed_dir() -> Path:
    """获取主工作目录"""
    return get_paths_config().seed_base

def get_memory_dir() -> Path:
    """获取记忆目录"""
    return get_paths_config().memory_dir

def get_logs_dir() -> Path:
    """获取日志目录"""
    return get_paths_config().logs_dir

def get_allowed_dirs() -> list[Path]:
    """获取允许访问的目录列表"""
    return get_paths_config().allowed_dirs


# ========== 其他配置类保持不变 ==========

@dataclass
class MemoryGraphConfig:
    half_life_days: int = 30
    # ... 保持原有定义

# ... 其他配置类
```

### 4.2 PathValidationConfig 改造

```python
@dataclass
class PathValidationConfig:
    """路径验证配置"""
    
    # 移除硬编码，从 PathsConfig 动态获取
    @property
    def project_root(self) -> Path:
        return get_paths_config().project_root
    
    @property
    def default_work_dir(self) -> Path:
        return get_paths_config().seed_base
    
    @property
    def allowed_dirs(self) -> list[Path]:
        return get_paths_config().allowed_dirs
```

---

## 五、迁移实施计划

### 5.1 第一阶段：核心改造

| 序号 | 文件 | 改动内容 | 验证方法 |
|------|------|----------|----------|
| 1 | `src/models.py` | 添加 PathsConfig、迁移函数、get_config_path() | 单元测试 |
| 2 | `src/shared_config.py` | 改造为动态读取 | 单元测试 |
| 3 | `src/client.py` | LLMGateway.__init__() 调用 init_paths_config() | 集成测试 |
| 4 | `main.py` | 使用 get_config_path()、移除硬编码路径 | 运行测试 |

### 5.2 第二阶段：文件迁移

| 序号 | 文件 | 改动内容 |
|------|------|----------|
| 5 | `src/security/credential_vault.py` | 使用 get_paths_config().vault_dir |
| 6 | `src/rate_limit_db.py` | 使用 get_paths_config().rate_limit_db |
| 7 | `src/tools/skill_cache.py` | 使用 get_paths_config().cache_dir |
| 8 | `src/tools/user_modeling.py` | 使用 get_paths_config().user_modeling_db |
| 9 | `src/tools/vision_api.py` | 使用 get_config_path() |
| 10 | `src/tools/long_term_archive.py` | 使用 get_paths_config().archives_db |

### 5.3 第三阶段：已迁移文件验证

以下文件已部分使用 shared_config，需验证兼容性：

| 文件 | 当前状态 | 验证点 |
|------|----------|--------|
| `src/tools/builtin_tools.py` | 已使用 shared_config | 确认 get_path_validation_config() 兼容 |
| `src/tools/memory_tools.py` | 已导入 SEED_DIR | 改用 get_memory_dir() |
| `src/tools/session_db.py` | 已使用 shared_config | 确认 DB_PATH 动态计算 |
| `src/tools/skill_loader.py` | 已导入 SEED_DIR | 改用 get_paths_config() |

### 5.4 配置文件示例

**最小配置** (新增用户):

```json
{
  "version": 3,
  "paths": {
    "seedBaseDir": "~/.seed"
  },
  "models": { ... },
  "agents": { ... }
}
```

**完整配置** (多环境用户):

```json
{
  "version": 3,
  "paths": {
    "seedBaseDir": "~/.seed",
    "projectRoot": "E:/projects/seed-agent",
    "wikiDir": "E:/projects/wiki",
    "allowedDirs": [
      "~/.seed",
      "~/Documents",
      "E:/projects/wiki",
      "D:/backup"
    ]
  },
  "models": { ... },
  "agents": { ... }
}
```

---

## 六、使用示例

### 6.1 默认使用

```bash
# 默认 ~/.seed/config.json
python main.py
```

### 6.2 自定义配置位置

```bash
# 生产环境
SEED_HOME=/data/seed python main.py

# 开发环境
SEED_HOME=./dev_seed python main.py

# Windows PowerShell
$env:SEED_HOME = "D:\seed"
python main.py
```

### 6.3 代码中使用

```python
from src.shared_config import get_paths_config, get_seed_dir

# 获取配置
paths = get_paths_config()

# 使用路径
memory_file = paths.memory_dir / "notes.md"
db_path = paths.sessions_db
allowed = paths.allowed_dirs

# 便利函数
seed_dir = get_seed_dir()
logs_dir = get_logs_dir()
```

---

## 七、风险与注意事项

### 7.1 迁移风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **配置文件缺失 paths 段** | 启动失败 | 自动迁移添加默认值 |
| **allowedDirs 未配置** | 权限验证失败 | 自动添加核心目录 |
| **SEED_HOME 指向不存在目录** | FileNotFoundError | 启动时检查并提示 |
| **路径权限问题** | 无法写入 | 启动时验证并提示 |

### 7.2 注意事项

1. **配置文件必须存在**: `config.json` 必须手动创建或使用模板
2. **路径展开**: 所有路径支持 `~` 和 `$ENV_VAR` 格式
3. **目录自动创建**: 子路径在首次使用时自动创建（保持现有行为）
4. **wikiDir 可选**: 未配置时 `get_paths_config().wiki_dir` 返回 `None`

---

## 八、附录

### A. 配置文件完整模板

```json
{
  "version": 3,
  "paths": {
    "seedBaseDir": "~/.seed",
    "projectRoot": null,
    "wikiDir": null,
    "allowedDirs": [
      "~/.seed",
      "~/Documents"
    ]
  },
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "api": "openai-completions",
      "models": [
        {
          "id": "qwen-coder-plus",
          "name": "Qwen Coder Plus",
          "contextWindow": 100000,
          "maxTokens": 4096
        }
      ],
      "rateLimit": {
        "rollingWindowRequests": 6000,
        "rollingWindowDuration": 18000,
        "burstCapacity": 100,
        "maxConcurrent": 3
      }
    }
  },
  "agents": {
    "defaults": {
      "defaults": {
        "primary": "bailian/qwen-coder-plus"
      }
    }
  }
}
```

### B. 环境变量参考

| 环境变量 | 用途 | 优先级 |
|----------|------|--------|
| `SEED_HOME` | 配置文件根目录 | 最高 |
| `BAILIAN_API_KEY` | API 密钥 | 被 config.json `${}` 引用 |
| `OTEL_ENABLED` | OpenTelemetry 开关 | 独立配置 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry 端点 | 独立配置 |

---

**文档结束**