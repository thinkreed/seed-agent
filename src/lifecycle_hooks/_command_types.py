"""命令钩子类型定义"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandHookConfig:
    """命令钩子配置"""

    command: str
    timeout: float = 30.0
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    capture_output: bool = True
    shell: bool = False


@dataclass
class CommandHookResult:
    """命令钩子执行结果"""

    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000] if self.stdout else "",
            "stderr": self.stderr[:1000] if self.stderr else "",
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


__all__ = ["CommandHookConfig", "CommandHookResult"]