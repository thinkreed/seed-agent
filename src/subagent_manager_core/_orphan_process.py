"""
Orphan Reaper 进程管理

包含进程状态检查和信号发送的跨平台实现。
"""

import os
import signal
import subprocess


def is_process_alive(pid: int) -> bool:
    """检查进程是否存活

    Args:
        pid: 进程 ID

    Returns:
        进程是否存活
    """
    try:
        # Windows 使用不同方式检查
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            # Unix/Linux: 发送 signal 0 检查
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, OSError):
        return False


def send_signal(pid: int, sig: int) -> None:
    """发送信号到进程

    在 Windows 上使用 taskkill 模拟 SIGTERM/SIGKILL 行为。

    Args:
        pid: 进程 ID
        sig: 信号（signal.SIGTERM 或 signal.SIGKILL）

    Raises:
        ProcessLookupError: 进程不存在（Unix）
        OSError: 系统错误
    """
    if os.name == "nt":
        # Windows 没有 SIGTERM/SIGKILL，使用 taskkill
        if sig == signal.SIGTERM:
            subprocess.run(["taskkill", "/PID", str(pid)], check=False, capture_output=True)
        else:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
    else:
        os.kill(pid, sig)