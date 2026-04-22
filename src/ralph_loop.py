"""Ralph Loop: 长周期确定性任务执行器

核心机制:
1. 外部验证驱动完成 - 由客观标准（测试/DONE标志）决定，而非模型自判
2. 每次迭代新鲜上下文 - 消除上下文漂移风险
3. 状态持久于文件系统 - 任务可恢复（进程崩溃后继续）
4. 防无限循环保护 - 迭代上限+时间上限双重保护

参考设计: docs/long_cycle_loop_enhancement_design.md
"""

import os
import time
import json
import asyncio
import subprocess
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, List
from enum import Enum

logger = logging.getLogger("seed_agent.ralph")

SEED_DIR = Path(os.path.expanduser("~")) / ".seed"


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
        agent_loop,
        completion_type: CompletionType,
        completion_criteria: dict,
        task_prompt_path: Path,
        on_iteration_complete: Callable = None,
        max_iterations: int = None,
        max_duration: int = None,
        context_reset_interval: int = None
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
        self._state_file: Path = SEED_DIR / "ralph" / f"task_{task_prompt_path.stem}_state.json"
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
            except Exception as e:
                logger.error(f"Agent execution failed at iteration {self._iteration_count}: {e}")
                response = f"Error: {str(e)}"

            # 5. 持久化状态
            self._persist_state(response)

            # 6. 外部完成验证
            if self._check_completion():
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
                    logger.warning(f"Callback failed: {e}")

            # 8. 等待下一轮
            await asyncio.sleep(1)

        return self._generate_status_report()

    def stop(self):
        """停止 Ralph Loop"""
        self._is_running = False
        logger.info(f"Ralph Loop stopped at iteration {self._iteration_count}")

    # === 完成验证 ===

    def _check_completion(self) -> bool:
        """外部完成验证（核心机制）"""
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
                result = validator()
                if result:
                    logger.info(f"Completion verified: {self.completion_type}")
                return result
            except Exception as e:
                logger.warning(f"Completion check failed: {e}")
                return False
        return False

    def _check_test_pass(self) -> bool:
        """检查测试通过率"""
        required_rate = self.completion_criteria.get("pass_rate", 100)
        test_command = self.completion_criteria.get("test_command", "pytest tests/ -v")
        cwd = self.completion_criteria.get("cwd", str(SEED_DIR))

        try:
            result = subprocess.run(
                test_command,
                shell=True,
                capture_output=True,
                cwd=cwd,
                timeout=300  # 5分钟超时
            )

            # 解析测试结果（pytest 输出）
            pass_rate = self._parse_test_pass_rate(result.stdout)

            logger.info(f"Test pass rate: {pass_rate}% (required: {required_rate}%)")
            return pass_rate >= required_rate
        except subprocess.TimeoutExpired:
            logger.warning("Test execution timed out")
            return False
        except Exception as e:
            logger.warning(f"Test execution failed: {e}")
            return False

    def _parse_test_pass_rate(self, output: str) -> float:
        """解析测试输出获取通过率"""
        # pytest 输出格式: "X passed, Y failed" 或 "X passed"
        import re

        # 尝试匹配 pytest 的输出格式
        passed_match = re.search(r'(\d+)\s+passed', output)
        failed_match = re.search(r'(\d+)\s+failed', output)
        error_match = re.search(r'(\d+)\s+error', output)

        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0

        total = passed + failed + errors
        if total == 0:
            return 0.0

        return (passed / total) * 100

    def _check_file_exists(self) -> bool:
        """检查目标文件存在"""
        files = self.completion_criteria.get("files", [])
        if not files:
            return False

        all_exist = all(Path(f).exists() for f in files)
        if all_exist:
            logger.info(f"All target files exist: {files}")
        return all_exist

    def _check_marker_file(self) -> bool:
        """检查完成标志文件"""
        marker_path = Path(self.completion_criteria.get("marker_path", SEED_DIR / "completion_marker"))
        marker_content = self.completion_criteria.get("marker_content", "DONE")

        if marker_path.exists():
            content = marker_path.read_text().strip()
            if content == marker_content:
                logger.info(f"Marker file verified: {marker_path}")
                # 可选：清除标志文件
                if self.completion_criteria.get("cleanup_marker", True):
                    marker_path.unlink()
                return True
        return False

    def _check_git_clean(self) -> bool:
        """检查 Git 工作区状态"""
        repo_path = self.completion_criteria.get("repo_path", str(SEED_DIR))

        try:
            result = subprocess.run(
                "git status --porcelain",
                shell=True,
                capture_output=True,
                cwd=repo_path,
                timeout=30
            )
            is_clean = result.stdout.strip() == ""
            if is_clean:
                logger.info("Git working directory is clean")
            return is_clean
        except Exception as e:
            logger.warning(f"Git check failed: {e}")
            return False

    def _check_custom(self) -> bool:
        """自定义验证函数"""
        checker = self.completion_criteria.get("checker")
        if checker and callable(checker):
            try:
                result = checker()
                logger.info(f"Custom check result: {result}")
                return bool(result)
            except Exception as e:
                logger.warning(f"Custom check failed: {e}")
                return False
        return False

    # === 上下文管理 ===

    def _reset_context(self):
        """重置上下文（新鲜上下文）"""
        # 每 ITERATION_INTERVAL 轮重置一次
        if self._iteration_count % self.context_reset_interval != 0:
            return

        # 提取关键上下文（可选）
        preserved = self._extract_critical_context()

        # 清空 history
        self.agent.history.clear()

        # 重新注入保留信息（如有）
        if preserved:
            self.agent.history.append({
                "role": "system",
                "content": f"[迭代 {self._iteration_count} 状态摘要]\n{preserved}"
            })

        logger.info(f"Context reset at iteration {self._iteration_count}")

    def _load_task_prompt(self) -> str:
        """加载任务 prompt（从文件）"""
        if self.task_prompt_path and self.task_prompt_path.exists():
            content = self.task_prompt_path.read_text()
            return f"[Ralph Loop 迭代 {self._iteration_count}]\n\n{content}"

        # 默认 prompt
        return f"继续执行任务。当前迭代: {self._iteration_count}"

    def _extract_critical_context(self) -> Optional[str]:
        """提取关键上下文（可选保留）"""
        if not self.agent.history:
            return None

        # 提取最后一条 assistant 消息的摘要
        for msg in reversed(self.agent.history):
            if msg.get("role") == "assistant" and msg.get("content"):
                return f"上次执行摘要: {msg['content'][:300]}"
        return None

    # === 状态持久化 ===

    def _load_or_init_state(self):
        """加载或初始化状态（支持进程恢复）"""
        if self._state_file.exists():
            try:
                state = json.loads(self._state_file.read_text())
                self._iteration_count = state.get("iteration", 0)
                self._accumulated_duration = state.get("accumulated_duration", 0)
                # FIX: 重置 start_time 为当前时间，而非使用旧时间戳
                self._start_time = time.time()
                logger.info(f"Resumed Ralph Loop from iteration {self._iteration_count}, "
                           f"accumulated: {self._accumulated_duration}s")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"State file corrupted, starting fresh: {e}")
                self._iteration_count = 0
                self._start_time = time.time()
                self._accumulated_duration = 0
        else:
            self._iteration_count = 0
            self._start_time = time.time()
            self._accumulated_duration = 0

    def _persist_state(self, response: str):
        """持久化当前状态"""
        # 计算当前会话已执行时间，累加到总时间
        current_elapsed = time.time() - self._start_time if self._start_time > 0 else 0
        total_accumulated = self._accumulated_duration + current_elapsed
        state = {
            "iteration": self._iteration_count,
            "accumulated_duration": total_accumulated,  # 保存累计时间
            "last_response": response[:500] if response else "",
            "timestamp": time.time(),
            "task_file": str(self.task_prompt_path),
            "completion_type": self.completion_type.value
        }
        self._state_file.write_text(json.dumps(state, indent=2))

    # === 安全机制 ===

    def _check_safety_limits(self) -> bool:
        """检查安全上限"""
        # 迭代上限
        if self._iteration_count >= self.max_iterations:
            logger.warning(f"Ralph Loop exceeded max iterations ({self.max_iterations})")
            return True

        # 时间上限（累计 + 当前会话）
        if self._start_time > 0:
            current_elapsed = time.time() - self._start_time
            total_elapsed = self._accumulated_duration + current_elapsed
            if total_elapsed >= self.max_duration:
                logger.warning(f"Ralph Loop exceeded max duration ({self.max_duration}s, "
                              f"accumulated: {self._accumulated_duration}s, current: {current_elapsed}s)")
                return True

        return False

    # === 辅助方法 ===

    def _cleanup(self):
        """清理状态文件"""
        if self._state_file.exists():
            self._state_file.unlink()
        logger.info("Ralph Loop cleanup completed")

    def _generate_status_report(self) -> str:
        """生成状态报告"""
        current_elapsed = time.time() - self._start_time
        total_elapsed = self._accumulated_duration + current_elapsed
        report = f"""
Ralph Loop Status Report:
- Task: {self.task_prompt_path}
- Iterations: {self._iteration_count}
- Total Duration: {total_elapsed/60:.1f} minutes (accumulated: {self._accumulated_duration/60:.1f} min)
- Exit Reason: Safety limit reached
- Completion Type: {self.completion_type.value}
- State File: {self._state_file}
"""
        logger.info(report)
        return report

    # === 工厂方法 ===

    @classmethod
    def create_test_driven(
        cls,
        agent_loop,
        task_prompt_path: Path,
        test_command: str = "pytest tests/ -v",
        pass_rate: float = 100
    ) -> 'RalphLoop':
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
        marker_path: Path = None,
        marker_content: str = "DONE"
    ) -> 'RalphLoop':
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
    completion_criteria: dict = None,
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