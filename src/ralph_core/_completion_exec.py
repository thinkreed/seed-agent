"""
Ralph Loop 完成验证 - 进程执行检查

处理需要异步进程执行的完成验证。
"""

import asyncio
import logging
import re
import shlex
from typing import Any

logger = logging.getLogger("seed_agent.ralph")

# 预编译正则表达式
_PASSED_PATTERN = re.compile(r"(\d+)\s+passed")
_FAILED_PATTERN = re.compile(r"(\d+)\s+failed")
_ERROR_PATTERN = re.compile(r"(\d+)\s+error")


class CompletionExecChecker:
    """进程执行完成验证器"""

    async def check_test_pass(self, criteria: dict[str, Any] | None) -> bool:
        """检查测试通过率"""
        if not criteria:
            return False

        required_rate = criteria.get("pass_rate", 100)
        test_command = criteria.get("test_command", "pytest tests/ -v")
        cwd = criteria.get("cwd", ".")

        proc: asyncio.subprocess.Process | None = None
        try:
            cmd_args = shlex.split(test_command)
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            pass_rate = self._parse_test_pass_rate(stdout)

            logger.info(f"Test pass rate: {pass_rate}% (required: {required_rate}%)")
            return pass_rate >= required_rate
        except TimeoutError:
            logger.warning("Test execution timed out")
            await self._terminate_process(proc)
            return False
        except Exception as e:
            logger.warning(f"Test execution failed: {type(e).__name__}: {e}")
            return False

    async def check_git_clean(self, criteria: dict[str, Any] | None) -> bool:
        """检查 Git 工作区状态"""
        if not criteria:
            return False
        repo_path = criteria.get("repo_path", ".")

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--porcelain",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=repo_path,
            )

            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            is_clean = stdout.strip() == b"" or stdout.strip() == ""
            if is_clean:
                logger.info("Git working directory is clean")
            return is_clean
        except TimeoutError:
            logger.warning("Git status check timed out")
            await self._terminate_process(proc)
            return False
        except FileNotFoundError:
            logger.warning("git command not found")
            return False
        except Exception as e:
            logger.warning(f"Git check failed: {type(e).__name__}: {e}")
            return False

    async def _terminate_process(self, proc: asyncio.subprocess.Process | None) -> None:
        """安全终止进程"""
        if proc is None or proc.returncode is not None:
            return

        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        except OSError as e:
            logger.warning(f"Error terminating process: {e}")

    def _parse_test_pass_rate(self, output: str | bytes) -> float:
        """解析测试输出获取通过率"""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")

        passed_match = _PASSED_PATTERN.search(output)
        failed_match = _FAILED_PATTERN.search(output)
        error_match = _ERROR_PATTERN.search(output)

        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0

        total = passed + failed + errors
        if total == 0:
            return 0.0

        return (passed / total) * 100