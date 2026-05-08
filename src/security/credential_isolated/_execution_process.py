"""
凭证隔离沙盒 - 进程级隔离执行模块

负责:
- 进程级隔离执行
- 安全参数传递（临时文件）
- 错误处理和超时
"""

import asyncio
import contextlib
import json
import logging
import os
import tempfile

from src.security.credential_isolated._environment import (
    detect_credential_access_attempt,
)
from src.security.credential_isolated._sanitize import (
    sanitize_error_message,
    sanitize_output,
)

logger = logging.getLogger(__name__)


async def execute_in_isolated_process(
    tool_name: str,
    args: dict,
    workspace_path: str,
    isolated_env: dict[str, str],
    enforce_credential_isolation: bool = True,
    timeout: float = 30.0,
) -> str:
    """进程级隔离执行（无凭证环境）

    创建隔离的子进程环境，移除所有敏感环境变量。
    使用临时文件传递参数，避免 f-string 代码注入风险。

    Args:
        tool_name: 工具名称
        args: 工具参数
        workspace_path: 工作目录
        isolated_env: 无凭证环境变量
        enforce_credential_isolation: 是否强制凭证隔离
        timeout: 执行超时

    Returns:
        执行结果

    Raises:
        RuntimeError: 执行失败或超时
    """
    # 检查是否尝试访问凭证
    args_str = json.dumps(args)
    if detect_credential_access_attempt(args_str, enforce=enforce_credential_isolation):
        logger.warning(f"Potential credential access attempt detected in tool: {tool_name}")
        return "[BLOCKED] Credential access attempt detected in sandbox"

    # 安全：使用临时文件传递参数，而非 f-string 嵌入
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as args_file:
        json.dump(args, args_file)
        args_file_path = args_file.name

    try:
        # 安全的执行脚本（参数从文件读取）
        safe_script = f"""
import json
import sys
args_file = sys.argv[1]
with open(args_file) as f:
    args = json.load(f)
from src.tools.builtin_tools import {tool_name}
result = {tool_name}(**args)
print(result)
"""

        # 创建子进程（无凭证环境）
        proc = await asyncio.create_subprocess_exec(
            "python",
            "-c",
            safe_script,
            args_file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=isolated_env,
            cwd=workspace_path,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        # 清理临时文件
        with contextlib.suppress(OSError):
            os.unlink(args_file_path)

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            safe_error = sanitize_error_message(error_msg)
            raise RuntimeError(safe_error)

        result = stdout.decode() if stdout else ""
        return sanitize_output(result)

    except TimeoutError:
        with contextlib.suppress(OSError):
            os.unlink(args_file_path)
        raise RuntimeError("Subprocess execution timeout") from None
    except Exception as e:
        with contextlib.suppress(OSError):
            os.unlink(args_file_path)
        raise RuntimeError(f"Subprocess execution failed: {type(e).__name__}") from e