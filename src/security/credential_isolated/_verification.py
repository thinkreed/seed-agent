"""
凭证隔离沙盒 - 验证模块

验证凭证隔离是否有效。
"""

import asyncio
from typing import Any

from ._environment import create_isolated_environment


async def verify_credential_isolation(
    blocked_env_vars: list[str],
) -> dict[str, Any]:
    """验证凭证隔离是否有效

    Args:
        blocked_env_vars: 屏蔽的环境变量列表

    Returns:
        验证结果
    """
    test_code = "import os; print(os.environ.get('OPENAI_API_KEY', 'NOT_FOUND'))"

    try:
        isolated_env = create_isolated_environment(blocked_env_vars)
        proc = await asyncio.create_subprocess_exec(
            "python",
            "-c",
            test_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=isolated_env,
        )

        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        result = stdout.decode().strip()

        is_isolated = result in {"NOT_FOUND", "None"} or not result

        return {
            "isolation_verified": is_isolated,
            "test_result": result if is_isolated else "[CONTAINS_CREDENTIAL]",
            "blocked_vars_count": len(blocked_env_vars),
        }

    except Exception as e:
        return {
            "isolation_verified": False,
            "error": str(e),
        }