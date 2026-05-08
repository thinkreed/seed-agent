"""
Orphan Reaper 类型定义

包含孤儿进程回收器所需的所有类型定义。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OrphanStatus(Enum):
    """孤儿进程状态"""
    ALIVE = "alive"           # 正常运行
    TIMEOUT = "timeout"       # 超时待处理
    TERMINATED = "terminated" # 已发送 SIGTERM
    KILLED = "killed"         # 已强制终止
    CLEANED = "cleaned"       # 已清理完成


@dataclass
class ProcessInfo:
    """进程信息"""
    pid: int
    task_id: str
    start_time: float
    timeout: float
    status: OrphanStatus = OrphanStatus.ALIVE
    terminate_time: float = 0.0
    kill_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReaperConfig:
    """Reaper 配置"""
    scan_interval: float = 30.0      # 扫描间隔（秒）
    terminate_timeout: float = 5.0   # SIGTERM 后等待时间
    max_grace_period: float = 60.0   # 最大宽限期（超时后）
    enable_logging: bool = True