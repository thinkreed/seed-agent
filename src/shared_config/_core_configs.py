"""核心配置数据类

包含 MemoryGraph、Queue、PathValidation、CodeExecution、Vision 配置。
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.shared_config._path_management import get_paths_config


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
class QueueConfig:
    """请求队列配置"""

    max_critical_dispatch_rate: float = 50.0
    max_background_dispatch_rate: float = 20.0
    queue_size_warning_threshold: int = 100
    queue_size_critical_threshold: int = 200


@dataclass
class PathValidationConfig:
    """路径验证配置（动态路径）"""

    @property
    def project_root(self) -> Path:
        try:
            return get_paths_config().project_root
        except RuntimeError:
            return Path(__file__).parent.parent.parent.resolve()

    @property
    def default_work_dir(self) -> Path:
        try:
            return get_paths_config().seed_base
        except RuntimeError:
            return Path.home() / ".seed"

    @property
    def allowed_dirs(self) -> list[Path]:
        try:
            return get_paths_config().allowed_dirs_resolved
        except RuntimeError:
            return [
                self.default_work_dir,
                self.project_root,
                Path.home() / "Documents",
            ]


@dataclass
class CodeExecutionSecurityConfig:
    """代码执行安全配置"""

    shell_blacklist: list[str] = field(
        default_factory=lambda: [
            "rm -rf", "rm -r", "rmdir", "del ", "format", "dd",
            "mkfs", "fdisk", "parted", "gdisk", "sfdisk",
            "sudo", "su", "chmod 777", "chown",
            "wget", "curl -o", "nc ", "netcat", "telnet",
            "kill -9", "pkill", "killall",
            "; rm", "| rm", "& rm", "`rm", "$(rm",
            "cat /etc/passwd", "cat /etc/shadow",
            "sysctl", "iptables", "ufw",
            "systemctl disable", "shutdown", "reboot", "halt", "poweroff",
            "apt install", "yum install", "dnf install", "pip install",
        ]
    )

    powershell_blacklist: list[str] = field(
        default_factory=lambda: [
            "Remove-Item", "Delete-Item", "Format-Volume",
            "Set-ExecutionPolicy", "Start-Process -Verb RunAs",
            "Download-File", "Invoke-WebRequest -OutFile",
            "Stop-Process -Force", "Kill-Process",
            "Set-ItemProperty", "New-ItemProperty", "Remove-ItemProperty",
            "Disable-ComputerRestore", "Clear-EventLog",
            "Invoke-Command", "Enter-PSSession", "New-SSHSession",
            "Initialize-Disk", "Clear-Disk", "Remove-Partition",
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


# ========== 全局配置实例 ==========

_memory_graph_config = MemoryGraphConfig()
_queue_config = QueueConfig()
_path_validation_config = PathValidationConfig()
_code_execution_security_config = CodeExecutionSecurityConfig()
_vision_config = VisionConfig()


def get_memory_graph_config() -> MemoryGraphConfig:
    """获取 Memory Graph 配置"""
    return _memory_graph_config


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
    """从 Gateway 配置获取主模型 ID"""
    return gateway.config.agents["defaults"].defaults.primary