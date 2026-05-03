"""
共享配置模块 - 提取各模块的硬编码常量

统一管理:
- Memory Graph 参数
- Subagent 超时配置
- 路径验证配置
- 代码执行安全规则
- SEED 目录路径

便于用户覆盖和维护更新。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# 统一 SEED 目录定义（避免多文件重复定义）
SEED_DIR = Path.home() / ".seed"


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

    # 不同类型任务的默认超时时间
    # EXPLORE: 快速查询 (3m)
    # REVIEW: 审查+测试 (10m)
    # IMPLEMENT: 实现+调试 (15m)
    # PLAN: 规划分析 (5m)
    explore: int = 180
    review: int = 600
    implement: int = 900
    plan: int = 300

    max_iterations: int = 15  # 最大迭代次数


@dataclass
class RalphLoopConfig:
    """Ralph Loop 配置"""

    max_iterations: int = 1000  # 最大迭代次数
    max_duration_hours: int = 8  # 最大执行时间（小时）
    context_reset_interval: int = 50  # 上下文重置间隔（迭代次数）


@dataclass
class AutonomousConfig:
    """自主探索配置"""

    idle_timeout_hours: int = 2  # 空闲触发时间（小时）
    completion_prompt_tokens: int = 500  # 完成提示 token 数
    max_exploration_rounds: int = 5  # 最大探索轮数


@dataclass
class QueueConfig:
    """请求队列配置"""

    max_critical_dispatch_rate: float = 50.0  # VIP 最大调度速率
    max_background_dispatch_rate: float = 20.0  # 后台最大调度速率
    queue_size_warning_threshold: int = 100  # 队列大小警告阈值
    queue_size_critical_threshold: int = 200  # 队列大小临界阈值


@dataclass
class PathValidationConfig:
    """路径验证配置"""

    # 默认工作目录为 ~/.seed 目录
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    default_work_dir: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~")) / ".seed"
    )

    # 允许的目录列表（可扩展）
    allowed_dirs: list[Path] = field(default_factory=list)

    def __post_init__(self):
        """初始化默认允许目录"""
        if not self.allowed_dirs:
            self.allowed_dirs = [
                self.default_work_dir,
                self.project_root,
                Path(os.path.expanduser("~")) / "Documents",
            ]


@dataclass
class CodeExecutionSecurityConfig:
    """代码执行安全配置"""

    # Shell 黑名单（系统破坏性命令）
    # 扩展包含：磁盘操作、系统配置、网络工具等
    shell_blacklist: list[str] = field(
        default_factory=lambda: [
            # 文件/目录删除
            "rm -rf",
            "rm -r",
            "rmdir",
            "del ",
            "format",
            # 磁盘操作（新增）
            "dd",
            "mkfs",
            "fdisk",
            "parted",
            "gdisk",
            "sfdisk",
            # 权限提升
            "sudo",
            "su",
            "chmod 777",
            "chown",
            # 网络工具（潜在数据泄露）
            "wget",
            "curl -o",
            "nc ",
            "netcat",
            "telnet",
            # 进程终止
            "kill -9",
            "pkill",
            "killall",
            # 命令注入模式
            "; rm",
            "| rm",
            "& rm",
            "`rm",
            "$(rm",
            # 敏感文件访问
            "cat /etc/passwd",
            "cat /etc/shadow",
            # 系统配置修改（新增）
            "sysctl",
            "iptables",
            "ufw",
            "systemctl disable",
            "shutdown",
            "reboot",
            "halt",
            "poweroff",
            # 包管理器（可能安装恶意软件）
            "apt install",
            "yum install",
            "dnf install",
            "pip install",
        ]
    )

    # PowerShell 黑名单
    # 扩展包含：磁盘操作、系统配置、远程执行等
    powershell_blacklist: list[str] = field(
        default_factory=lambda: [
            # 文件删除
            "Remove-Item",
            "Delete-Item",
            "Format-Volume",
            # 权限/执行策略
            "Set-ExecutionPolicy",
            "Start-Process -Verb RunAs",
            # 网络下载
            "Download-File",
            "Invoke-WebRequest -OutFile",
            # 进程终止
            "Stop-Process -Force",
            "Kill-Process",
            # 系统配置（新增）
            "Set-ItemProperty",
            "New-ItemProperty",
            "Remove-ItemProperty",
            "Disable-ComputerRestore",
            "Clear-EventLog",
            # 远程执行（新增）
            "Invoke-Command",
            "Enter-PSSession",
            "New-SSHSession",
            # 磁盘操作（新增）
            "Initialize-Disk",
            "Clear-Disk",
            "Remove-Partition",
        ]
    )

    # 代码长度限制
    max_code_length: int = 10000

    # 默认超时
    default_timeout: int = 60


@dataclass
class VisionConfig:
    """视觉处理配置"""

    max_pixels: int = 1_440_000  # 最大像素数
    max_file_size_mb: int = 20  # 最大文件大小 (MB)
    supported_formats: list[str] = field(
        default_factory=lambda: ["png", "jpg", "jpeg", "gif", "webp"]
    )


# 全局配置实例（单例模式）
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
