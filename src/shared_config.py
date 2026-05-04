"""
共享配置模块 - 统一路径管理

改动：
1. 移除 SEED_DIR 硬编码
2. 从 PathsConfig 动态读取路径
3. 提供全局 PathsConfig 访问接口
4. 其他配置类保持不变

统一管理:
- Memory Graph 参数
- Subagent 超时配置
- 路径验证配置（动态）
- 代码执行安全规则
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.models import PathsConfig

# 全局 PathsConfig 实例（延迟初始化）
_paths_config: Optional["PathsConfig"] = None


def init_paths_config(config: "PathsConfig") -> None:
    """初始化全局路径配置

    Args:
        config: PathsConfig 实例

    Raises:
        RuntimeError: 重复初始化
    """
    global _paths_config
    if _paths_config is not None:
        raise RuntimeError("PathsConfig 已经初始化，不可重复调用")
    _paths_config = config


def get_paths_config() -> "PathsConfig":
    """获取全局路径配置

    Returns:
        PathsConfig: 路径配置实例

    Raises:
        RuntimeError: 未初始化
    """
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


def get_tasks_dir() -> Path:
    """获取任务目录"""
    return get_paths_config().tasks_dir


def get_cache_dir() -> Path:
    """获取缓存目录"""
    return get_paths_config().cache_dir


def get_sandbox_dir() -> Path:
    """获取沙盒目录"""
    return get_paths_config().sandbox_dir


def get_ralph_dir() -> Path:
    """获取 Ralph Loop 目录"""
    return get_paths_config().ralph_dir


def get_vault_dir() -> Path:
    """获取凭证存储目录"""
    return get_paths_config().vault_dir


def get_allowed_dirs() -> list[Path]:
    """获取允许访问的目录列表"""
    return get_paths_config().allowed_dirs_resolved


def get_project_root() -> Path:
    """获取项目根目录"""
    return get_paths_config().project_root


def get_wiki_dir() -> Path | None:
    """获取 Wiki 目录"""
    return get_paths_config().wiki_dir


# ========== 带 Fallback 的路径函数（用于初始化前场景） ==========


def get_seed_dir_with_fallback() -> Path:
    """获取主工作目录（带 fallback）

    用于 PathsConfig 未初始化时的场景（如模块导入时）
    """
    try:
        return get_paths_config().seed_base
    except RuntimeError:
        return Path.home() / ".seed"


def get_memory_dir_with_fallback() -> Path:
    """获取记忆目录（带 fallback）"""
    try:
        return get_paths_config().memory_dir
    except RuntimeError:
        return Path.home() / ".seed" / "memory"


def get_ralph_dir_with_fallback() -> Path:
    """获取 Ralph Loop 目录（带 fallback）"""
    try:
        return get_paths_config().ralph_dir
    except RuntimeError:
        return Path.home() / ".seed" / "ralph"


def get_tasks_dir_with_fallback() -> Path:
    """获取任务目录（带 fallback）"""
    try:
        return get_paths_config().tasks_dir
    except RuntimeError:
        return Path.home() / ".seed" / "tasks"


def get_cache_dir_with_fallback() -> Path:
    """获取缓存目录（带 fallback）"""
    try:
        return get_paths_config().cache_dir
    except RuntimeError:
        return Path.home() / ".seed" / "cache"


def get_sandbox_dir_with_fallback() -> Path:
    """获取沙盒目录（带 fallback）"""
    try:
        return get_paths_config().sandbox_dir
    except RuntimeError:
        return Path.home() / ".seed" / "sandbox"


# ========== 其他配置类（保持不变）==========


@dataclass
class MemoryGraphConfig:
    """Memory Graph 配置参数"""

    half_life_days: int = 30  # 置信度衰减半衰期
    ban_threshold: float = 0.18  # 禁用阈值
    min_attempts_for_ban: int = 2  # 禁用前最小尝试次数
    memory_weight: float = 0.6  # 记忆分数权重
    trigger_weight: float = 0.4  # 触发匹配权重
    cold_start_penalty: float = 0.5  # 冷启动惩罚因子
    recent_boost_factor: float = 0.2  # 近期成功加成因子
    recent_days: int = 30  # "近期"定义天数
    max_entries_per_skill: int = 5000  # 每个 skill 最大记录数


@dataclass
class SubagentTimeoutConfig:
    """Subagent 超时配置（秒）"""

    explore: int = 180  # EXPLORE: 快速查询 (3m)
    review: int = 600  # REVIEW: 审查+测试 (10m)
    implement: int = 900  # IMPLEMENT: 实现+调试 (15m)
    plan: int = 300  # PLAN: 规划分析 (5m)
    max_iterations: int = 15  # 最大迭代次数


@dataclass
class RalphLoopConfig:
    """Ralph Loop 配置"""

    max_iterations: int = 1000  # 最大迭代次数
    max_duration_hours: int = 8  # 最大执行时间（小时）
    context_reset_interval: int = 50  # 上下文重置间隔（迭代次数）


@dataclass
class AutonomousConfig:
    """自主探索配置（方案 A+C 整合：配置化上限 + 渐进式预算）

    多层防御体系：
    - Layer 1: 预算警告注入（70%/90%阈值）
    - Layer 2: 进度检测窗口（空转循环识别）
    - Layer 3: 时间断路器（单任务时间上限）
    - Layer 4: 递减重试预算（失败重试递减）
    - 安全上限: 1000轮 + 8小时（继承 RalphLoop）
    """

    # === 现有字段 ===
    idle_timeout_hours: int = 2  # 空闲触发时间（小时）
    completion_prompt_tokens: int = 500  # 完成提示 token 数
    max_exploration_rounds: int = 5  # 最大探索轮数

    # 超时保护
    llm_call_timeout_seconds: int = 300  # LLM 单次调用超时（5分钟）
    iteration_timeout_seconds: int = 600  # 单轮迭代总超时（10分钟）

    # Ask User 跳过策略
    ask_user_skip_response: str = "[AUTONOMOUS_SKIP] 自主模式自动跳过用户确认，继续执行"
    ask_user_auto_confirm: bool = True

    # 错误恢复退避
    consecutive_failure_threshold: int = 3
    backoff_duration_seconds: int = 60
    max_backoff_multiplier: int = 5

    # 调试日志
    debug_logging_enabled: bool = True

    # === 方案 A: 配置化上限 ===
    max_iterations_per_task: int = 100  # 单任务迭代上限（可配置）
    max_iterations_high: int = 300  # 高复杂度任务上限
    max_iterations_research: int = 500  # 研究型任务上限
    max_duration_per_task: int = 1800  # 单任务时间上限（秒，30分钟）
    max_retry_count: int = 3  # 最大重试次数

    # === 方案 C: 渐进式预算 ===
    budget_warning_threshold: float = 0.70  # 预算警告阈值（70%）
    budget_urgent_threshold: float = 0.90  # 紧急警告阈值（90%）
    progress_detection_window: int = 5  # 进度检测窗口大小（连续N轮）
    time_warning_threshold: float = 0.80  # 时间警告阈值（80%）
    retry_decay_factors: list[float] = field(
        default_factory=lambda: [1.0, 0.5, 0.25]  # 首次100%, 二次50%, 三次25%
    )
    meaningful_tools: list[str] = field(
        default_factory=lambda: [
            "file_read",
            "file_write",
            "file_edit",
            "code_as_policy",
            "search_grep",
            "search_glob",
        ]
    )


@dataclass
class QueueConfig:
    """请求队列配置"""

    max_critical_dispatch_rate: float = 50.0
    max_background_dispatch_rate: float = 20.0
    queue_size_warning_threshold: int = 100
    queue_size_critical_threshold: int = 200


@dataclass
class PathValidationConfig:
    """路径验证配置（动态路径）"""

    # 所有路径从 PathsConfig 动态获取
    # 当 PathsConfig 未初始化时返回 fallback 值
    @property
    def project_root(self) -> Path:
        try:
            return get_paths_config().project_root
        except RuntimeError:
            # Fallback: 从 shared_config.py 所在目录向上查找
            return Path(__file__).parent.parent.resolve()

    @property
    def default_work_dir(self) -> Path:
        try:
            return get_paths_config().seed_base
        except RuntimeError:
            # Fallback: 使用默认 ~/.seed
            return Path.home() / ".seed"

    @property
    def allowed_dirs(self) -> list[Path]:
        try:
            return get_paths_config().allowed_dirs_resolved
        except RuntimeError:
            # Fallback: 使用默认允许目录
            return [
                self.default_work_dir,
                self.project_root,
                Path.home() / "Documents",
            ]


@dataclass
class CodeExecutionSecurityConfig:
    """代码执行安全配置"""

    # Shell 黑名单
    shell_blacklist: list[str] = field(
        default_factory=lambda: [
            "rm -rf",
            "rm -r",
            "rmdir",
            "del ",
            "format",
            "dd",
            "mkfs",
            "fdisk",
            "parted",
            "gdisk",
            "sfdisk",
            "sudo",
            "su",
            "chmod 777",
            "chown",
            "wget",
            "curl -o",
            "nc ",
            "netcat",
            "telnet",
            "kill -9",
            "pkill",
            "killall",
            "; rm",
            "| rm",
            "& rm",
            "`rm",
            "$(rm",
            "cat /etc/passwd",
            "cat /etc/shadow",
            "sysctl",
            "iptables",
            "ufw",
            "systemctl disable",
            "shutdown",
            "reboot",
            "halt",
            "poweroff",
            "apt install",
            "yum install",
            "dnf install",
            "pip install",
        ]
    )

    # PowerShell 黑名单
    powershell_blacklist: list[str] = field(
        default_factory=lambda: [
            "Remove-Item",
            "Delete-Item",
            "Format-Volume",
            "Set-ExecutionPolicy",
            "Start-Process -Verb RunAs",
            "Download-File",
            "Invoke-WebRequest -OutFile",
            "Stop-Process -Force",
            "Kill-Process",
            "Set-ItemProperty",
            "New-ItemProperty",
            "Remove-ItemProperty",
            "Disable-ComputerRestore",
            "Clear-EventLog",
            "Invoke-Command",
            "Enter-PSSession",
            "New-SSHSession",
            "Initialize-Disk",
            "Clear-Disk",
            "Remove-Partition",
        ]
    )

    max_code_length: int = 10000
    default_timeout: int = 60


@dataclass
class VisionConfig:
    """视觉处理配置"""

    max_pixels: int = 1_440_000
    max_file_size_mb: int = 20
    supported_formats: list[str] = field(
        default_factory=lambda: ["png", "jpg", "jpeg", "gif", "webp"]
    )


# ========== 全局配置实例（单例模式）==========

_memory_graph_config = MemoryGraphConfig()
_subagent_timeout_config = SubagentTimeoutConfig()
_ralph_loop_config = RalphLoopConfig()
_autonomous_config = AutonomousConfig()
_queue_config = QueueConfig()
_path_validation_config = PathValidationConfig()
_code_execution_security_config = CodeExecutionSecurityConfig()
_vision_config = VisionConfig()


def get_memory_graph_config() -> MemoryGraphConfig:
    """获取 Memory Graph 配置"""
    return _memory_graph_config


def get_subagent_timeout_config() -> SubagentTimeoutConfig:
    """获取 Subagent 超时配置"""
    return _subagent_timeout_config


def get_ralph_loop_config() -> RalphLoopConfig:
    """获取 Ralph Loop 配置"""
    return _ralph_loop_config


def get_autonomous_config() -> AutonomousConfig:
    """获取自主探索配置"""
    return _autonomous_config


def get_queue_config() -> QueueConfig:
    """获取请求队列配置"""
    return _queue_config


def get_path_validation_config() -> PathValidationConfig:
    """获取路径验证配置"""
    return _path_validation_config


def get_code_execution_security_config() -> CodeExecutionSecurityConfig:
    """获取代码执行安全配置"""
    return _code_execution_security_config


def get_vision_config() -> VisionConfig:
    """获取视觉处理配置"""
    return _vision_config


def get_primary_model(gateway) -> str:
    """从 Gateway 配置获取主模型 ID

    Args:
        gateway: LLMGateway 实例

    Returns:
        str: 主模型 ID
    """
    return gateway.config.agents["defaults"].defaults.primary