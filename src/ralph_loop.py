"""Ralph Loop: 长周期确定性任务执行器

核心机制:
1. 外部验证驱动完成 - 由客观标准（测试/DONE标志）决定，而非模型自判
2. 每次迭代新鲜上下文 - 消除上下文漂移风险
3. 状态持久于文件系统 - 任务可恢复（进程崩溃后继续）
4. 防无限循环保护 - 迭代上限+时间上限双重保护

参考设计: docs/long_cycle_loop_enhancement_design.md
"""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Coroutine
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from src.errors import ConfigurationError, ErrorSeverity, SeedAgentError, classify_error

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.ralph_state import (
    SEED_DIR,
    check_safety_limits,
    cleanup_state_file,
    extract_critical_context,
    generate_status_report,
    load_or_init_state,
    persist_state,
    reset_context,
)

# 预编译正则表达式（性能优化）
_PASSED_PATTERN = re.compile(r"(\d+)\s+passed")
_FAILED_PATTERN = re.compile(r"(\d+)\s+failed")
_ERROR_PATTERN = re.compile(r"(\d+)\s+error")

logger = logging.getLogger("seed_agent.ralph")


class CompletionType(Enum):
    """完成验证类型"""
    TEST_PASS = "test_pass"         # 测试通过
    FILE_EXISTS = "file_exists"     # 目标文件存在
    MARKER_FILE = "marker_file"     # 完成标志文件
    GIT_CLEAN = "git_clean"         # Git 工作区干净
    CUSTOM_CHECK = "custom_check"   # 自定义验证函数


class RalphLoop:
    """Ralph Loop 执行器

    核心机制:
    1. 外部验证驱动完成
    2. 每次迭代新鲜上下文
    3. 状态持久于文件系统
    4. 防无限循环保护

    使用示例:
        ralph = RalphLoop(
            agent_loop=agent,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={"marker_path": ".seed/done"},
            task_prompt_path=Path(".seed/tasks/refactor.md")
        )
        result = await ralph.run()
    """

    # 默认配置
    MAX_ITERATIONS = 1000
    MAX_DURATION = 8 * 60 * 60  # 8小时
    ITERATION_INTERVAL = 5      # 上下文重置间隔

    def __init__(
        self,
        agent_loop: "AgentLoop",
        completion_type: CompletionType,
        completion_criteria: dict | None = None,
        task_prompt_path: Path | None = None,
        on_iteration_complete: Callable[[int, str], None] | Callable[[int, str], Coroutine[Any, Any, None]] | None = None,
        max_iterations: int | None = None,
        max_duration: int | None = None,
        context_reset_interval: int | None = None
    ):
        """初始化 Ralph Loop

        Args:
            agent_loop: AgentLoop 实例
            completion_type: 完成验证类型
            completion_criteria: 完成验证条件
            task_prompt_path: 任务描述文件路径
            on_iteration_complete: 每轮迭代完成回调
            max_iterations: 最大迭代次数（默认1000）
            max_duration: 最大执行时间（秒，默认8小时）
            context_reset_interval: 上下文重置间隔（默认5轮）
        """
        self.agent = agent_loop
        self.completion_type = completion_type
        self.completion_criteria = completion_criteria
        self.task_prompt_path = task_prompt_path
        self.on_iteration_complete = on_iteration_complete

        # 可配置的上限
        self.max_iterations = max_iterations or self.MAX_ITERATIONS
        self.max_duration = max_duration or self.MAX_DURATION
        self.context_reset_interval = context_reset_interval or self.ITERATION_INTERVAL

        # 运行状态
        self._iteration_count: int = 0
        self._start_time: float = 0  # 当前会话开始时间
        self._accumulated_duration: float = 0  # 累计执行时间（跨会话）
        # 状态文件名：使用任务文件名或 UUID（避免多实例冲突）
        state_name = task_prompt_path.stem if task_prompt_path else f"auto_{uuid.uuid4().hex[:8]}"
        self._state_file: Path = SEED_DIR / "ralph" / f"task_{state_name}_state.json"
        self._is_running: bool = False

    # === 核心方法 ===

    async def run(self) -> str:
        """执行 Ralph Loop

        Returns:
            "DONE" - 任务完成
            状态报告 - 达到上限时的报告
        """
        self._is_running = True
        self._start_time = time.time()
        self._iteration_count = 0

        # 确保状态目录存在
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载或初始化状态
        self._load_or_init_state()

        logger.info(f"Ralph Loop started: {self.task_prompt_path}")

        while self._is_running:
            self._iteration_count += 1

            # 1. 安全检查
            if self._check_safety_limits():
                break

            # 2. 上下文重置（新鲜上下文）
            self._reset_context()

            # 3. 加载任务 prompt
            prompt = self._load_task_prompt()

            # 4. 执行一轮 Agent Loop
            try:
                response = await self.agent.run(prompt)
            except ConfigurationError as e:
                # 配置错误：不可恢复，终止循环
                logger.critical(f"Configuration error at iteration {self._iteration_count}: {e}")
                self._cleanup()
                raise
            except SeedAgentError as e:
                # 已知错误类型：根据严重程度决定是否继续
                error_type, severity = e.error_type, e.severity
                if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
                    logger.error(f"Critical error at iteration {self._iteration_count}: {e}")
                    self._cleanup()
                    raise
                logger.warning(f"Recoverable error at iteration {self._iteration_count}: {e}")
                response = f"Error: {e!s}"
            except Exception as e:
                # 未知错误：分类后决定处理方式
                error_type, severity = classify_error(e)
                if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
                    logger.error(f"Severe unclassified error at iteration {self._iteration_count}: {error_type.value}: {e}")
                    self._cleanup()
                    raise
                logger.warning(f"Agent execution failed at iteration {self._iteration_count}: {e}")
                response = f"Error: {e!s}"

            # 5. 持久化状态
            self._persist_state(response)

            # 6. 外部完成验证（异步）
            if await self._check_completion():
                logger.info(f"Ralph Loop completed at iteration {self._iteration_count}")
                self._cleanup()
                return "DONE"

            # 7. 回调通知
            if self.on_iteration_complete:
                try:
                    if asyncio.iscoroutinefunction(self.on_iteration_complete):
                        await self.on_iteration_complete(self._iteration_count, response)
                    else:
                        self.on_iteration_complete(self._iteration_count, response)
                except Exception as e:
                    logger.warning(f"Callback failed: {type(e).__name__}: {e}")

            # 8. 等待下一轮
            await asyncio.sleep(1)

        return self._generate_status_report()

    def stop(self):
        """停止 Ralph Loop"""
        self._is_running = False
        logger.info(f"Ralph Loop stopped at iteration {self._iteration_count}")

    # === 完成验证 ===

    async def _check_completion(self) -> bool:
        """外部完成验证（核心机制）- 异步版本"""
        validators = {
            CompletionType.TEST_PASS: self._check_test_pass,
            CompletionType.FILE_EXISTS: self._check_file_exists,
            CompletionType.MARKER_FILE: self._check_marker_file,
            CompletionType.GIT_CLEAN: self._check_git_clean,
            CompletionType.CUSTOM_CHECK: self._check_custom,
        }

        validator = validators.get(self.completion_type)
        if validator:
            try:
                # 异步验证方法需要 await
                if asyncio.iscoroutinefunction(validator):
                    result = await validator()
                else:
                    result = validator()
                if result:
                    logger.info(f"Completion verified: {self.completion_type}")
                return result
            except Exception as e:
                logger.warning(f"Completion check failed: {type(e).__name__}: {e}")
                return False
        return False

    async def _check_test_pass(self) -> bool:
        """检查测试通过率"""
        if not self.completion_criteria:
            return False

        import shlex

        required_rate = self.completion_criteria.get("pass_rate", 100)
        test_command = self.completion_criteria.get("test_command", "pytest tests/ -v")
        cwd = self.completion_criteria.get("cwd", str(SEED_DIR))

        proc: asyncio.subprocess.Process | None = None
        try:
            # 安全处理：使用 shlex.split 避免 shell=True
            # 注意：这不支持复杂的 shell 管道/重定向，但对于测试命令足够
            cmd_args = shlex.split(test_command)

            # 使用异步 subprocess 避免阻塞事件循环
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            # 异步等待完成（5分钟超时）
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            # 解析测试结果（pytest 输出）
            pass_rate = self._parse_test_pass_rate(stdout)

            logger.info(f"Test pass rate: {pass_rate}% (required: {required_rate}%)")
            return pass_rate >= required_rate
        except asyncio.TimeoutError:
            logger.warning("Test execution timed out")
            # 终止超时进程（使用辅助方法）
            await self._terminate_process(proc)
            return False
        except (ValueError, FileNotFoundError, PermissionError) as e:
            logger.warning(f"Test command setup failed: {type(e).__name__}: {e}")
            return False
        except Exception as e:
            logger.warning(f"Test execution failed: {type(e).__name__}: {e}")
            return False

    async def _terminate_process(self, proc: asyncio.subprocess.Process | None) -> None:
        """安全终止进程（避免重复代码）"""
        if proc is None:
            return
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass  # 进程已结束
        except OSError as e:
            logger.warning(f"Error killing process: {type(e).__name__}: {e}")
        except asyncio.CancelledError:
            # 取消时强制终止进程
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
            raise  # 传播取消信号

    def _parse_test_pass_rate(self, output: str | bytes) -> float:
        """解析测试输出获取通过率"""
        # 处理 bytes 类型
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")

        # 使用预编译正则匹配 pytest 输出格式
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

    def _check_file_exists(self) -> bool:
        """检查目标文件存在"""
        if not self.completion_criteria:
            return False
        files = self.completion_criteria.get("files", [])
        if not files:
            return False

        all_exist = all(Path(f).exists() for f in files)
        if all_exist:
            logger.info(f"All target files exist: {files}")
        return all_exist

    def _check_marker_file(self) -> bool:
        """检查完成标志文件"""
        if not self.completion_criteria:
            return False
        marker_path = Path(self.completion_criteria.get("marker_path", SEED_DIR / "completion_marker"))
        marker_content = self.completion_criteria.get("marker_content", "DONE")

        try:
            if marker_path.exists():
                content = marker_path.read_text(encoding="utf-8").strip()
                if content == marker_content:
                    logger.info(f"Marker file verified: {marker_path}")
                    # 可选：清除标志文件
                    if self.completion_criteria.get("cleanup_marker", True):
                        try:
                            marker_path.unlink()
                        except OSError as e:
                            logger.warning(f"Failed to cleanup marker file: {e}")
                    return True
        except (PermissionError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to check marker file {marker_path}: {e}")
        return False

    async def _check_git_clean(self) -> bool:
        """检查 Git 工作区状态（异步版本，不阻塞事件循环）"""
        if not self.completion_criteria:
            return False
        repo_path = self.completion_criteria.get("repo_path", str(SEED_DIR))

        try:
            # 使用异步 subprocess 执行 git 命令
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=repo_path
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            is_clean = stdout.strip() == b"" or stdout.strip() == ""
            if is_clean:
                logger.info("Git working directory is clean")
            return is_clean
        except asyncio.TimeoutError:
            logger.warning("Git status check timed out")
            return False
        except FileNotFoundError:
            logger.warning("git command not found")
            return False
        except Exception as e:
            logger.warning(f"Git check failed: {type(e).__name__}: {e}")
            return False

    async def _check_custom(self) -> bool:
        """自定义验证函数（支持异步）"""
        if not self.completion_criteria:
            return False
        checker = self.completion_criteria.get("checker")
        if checker and callable(checker):
            try:
                # 支持异步验证函数
                if asyncio.iscoroutinefunction(checker):
                    result = await checker()
                else:
                    result = checker()
                logger.info(f"Custom check result: {result}")
                return bool(result)
            except Exception as e:
                logger.warning(f"Custom check failed: {type(e).__name__}: {e}")
                return False
        return False

    # === 上下文管理 ===

    def _reset_context(self):
        """重置上下文（新鲜上下文，使用共享模块）"""
        # 提取关键上下文
        preserved = extract_critical_context(self.agent.history)

        # 使用共享模块执行重置
        reset_context(
            history=self.agent.history,
            iteration=self._iteration_count,
            reset_interval=self.context_reset_interval,
            preserved_context=preserved,
        )

    def _load_task_prompt(self) -> str:
        """加载任务 prompt（从文件）"""
        if self.task_prompt_path and self.task_prompt_path.exists():
            try:
                content = self.task_prompt_path.read_text(encoding="utf-8")
                return f"[Ralph Loop 迭代 {self._iteration_count}]\n\n{content}"
            except (PermissionError, OSError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to load task prompt from {self.task_prompt_path}: {e}")
        # 默认 prompt
        return f"继续执行任务。当前迭代: {self._iteration_count}"

    # === 状态持久化 ===

    def _load_or_init_state(self):
        """加载或初始化状态（支持进程恢复，使用共享模块）"""
        state = load_or_init_state(self._state_file)
        self._iteration_count = state.iteration
        self._accumulated_duration = state.accumulated_duration
        self._start_time = state.start_time

    def _persist_state(self, response: str):
        """持久化当前状态（使用共享模块）"""
        persist_state(
            state_file=self._state_file,
            iteration=self._iteration_count,
            start_time=self._start_time,
            accumulated_duration=self._accumulated_duration,
            response=response,
            task_file=str(self.task_prompt_path) if self.task_prompt_path else "",
            completion_type=self.completion_type.value,
        )

    # === 安全机制 ===

    def _check_safety_limits(self) -> bool:
        """检查安全上限（使用共享模块）"""
        return check_safety_limits(
            iteration=self._iteration_count,
            max_iterations=self.max_iterations,
            start_time=self._start_time,
            accumulated_duration=self._accumulated_duration,
            max_duration=self.max_duration,
        )

    # === 辅助方法 ===

    def _cleanup(self):
        """清理状态文件（使用共享模块）"""
        cleanup_state_file(self._state_file)

    def _generate_status_report(self) -> str:
        """生成状态报告（使用共享模块）"""
        return generate_status_report(
            task_file=str(self.task_prompt_path) if self.task_prompt_path else "",
            iteration=self._iteration_count,
            start_time=self._start_time,
            accumulated_duration=self._accumulated_duration,
            completion_type=self.completion_type.value,
            state_file=self._state_file,
        )

    # === 工厂方法 ===

    @classmethod
    def create_test_driven(
        cls,
        agent_loop,
        task_prompt_path: Path,
        test_command: str = "pytest tests/ -v",
        pass_rate: float = 100
    ) -> "RalphLoop":
        """创建测试驱动的 Ralph Loop"""
        return cls(
            agent_loop=agent_loop,
            completion_type=CompletionType.TEST_PASS,
            completion_criteria={
                "test_command": test_command,
                "pass_rate": pass_rate
            },
            task_prompt_path=task_prompt_path
        )

    @classmethod
    def create_marker_driven(
        cls,
        agent_loop,
        task_prompt_path: Path,
        marker_path: Path | None = None,
        marker_content: str = "DONE"
    ) -> "RalphLoop":
        """创建标志文件驱动的 Ralph Loop"""
        return cls(
            agent_loop=agent_loop,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={
                "marker_path": str(marker_path or SEED_DIR / "completion_marker"),
                "marker_content": marker_content
            },
            task_prompt_path=task_prompt_path
        )


async def create_ralph_loop(
    agent_loop,
    task_file: str,
    completion_type: str = "marker_file",
    completion_criteria: dict | None = None,
    **kwargs
) -> RalphLoop:
    """创建 Ralph Loop 实例

    Args:
        agent_loop: AgentLoop 实例
        task_file: 任务描述文件路径
        completion_type: 完成验证类型 (test_pass/file_exists/marker_file/git_clean/custom_check)
        completion_criteria: 完成验证条件
        **kwargs: 其他 RalphLoop 参数

    Returns:
        RalphLoop 实例
    """
    # 解析完成类型
    type_map = {
        "test_pass": CompletionType.TEST_PASS,
        "file_exists": CompletionType.FILE_EXISTS,
        "marker_file": CompletionType.MARKER_FILE,
        "git_clean": CompletionType.GIT_CLEAN,
        "custom_check": CompletionType.CUSTOM_CHECK,
    }

    c_type = type_map.get(completion_type, CompletionType.MARKER_FILE)
    criteria = completion_criteria or {}

    # 解析任务文件路径
    task_path = Path(task_file)
    if not task_path.is_absolute():
        task_path = SEED_DIR / "tasks" / task_file

    return RalphLoop(
        agent_loop=agent_loop,
        completion_type=c_type,
        completion_criteria=criteria,
        task_prompt_path=task_path,
        **kwargs
    )
