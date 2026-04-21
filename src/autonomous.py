"""自主探索模块：空闲时根据 SOP 执行自主任务

增强版 (Ralph Loop + Memory Graph 集成):
- completion_promise 检测：外部完成标志驱动退出
- 可选上下文重置：防止上下文漂移
- 防无限循环上限：迭代和时间双重保护
- Memory Graph 选择：基于历史结果选择最佳 Skill
- 自动结果记录：执行完成后自动记录 outcome
"""

import os
import asyncio
import time
import json
from pathlib import Path
from typing import Optional, Callable, Dict, List
from enum import Enum
import logging

logger = logging.getLogger("seed_agent")

# 项目根目录（当前文件所在目录的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
# SOP 文档路径
SOP_PATH = PROJECT_ROOT / "auto" / "自主探索 SOP.md"
SEED_DIR = Path(os.path.expanduser("~")) / ".seed"

# Ralph Loop 增强配置
COMPLETION_PROMISE_FILE = SEED_DIR / "completion_promise"
COMPLETION_PROMISE_TOKENS = ["DONE", "COMPLETE", "TASK_FINISHED"]
CONTEXT_RESET_ENABLED = True  # 默认开启
CONTEXT_RESET_INTERVAL = 5    # 每5轮迭代重置
RALPH_MAX_ITERATIONS = 1000   # 理论上限
RALPH_MAX_DURATION = 8 * 60 * 60  # 8小时最大执行时间


class CompletionType(Enum):
    """完成验证类型"""
    TEST_PASS = "test_pass"         # 测试通过
    FILE_EXISTS = "file_exists"     # 目标文件存在
    MARKER_FILE = "marker_file"     # 完成标志文件
    GIT_CLEAN = "git_clean"         # Git 工作区干净
    CUSTOM_CHECK = "custom_check"   # 自定义验证函数


class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强)

    新增特性:
    - completion_promise 检测：外部标志驱动退出
    - 可选上下文重置：防止上下文漂移
    - 防无限循环上限：迭代和时间双重保护
    """

    IDLE_TIMEOUT = 30 * 60  # 30分钟（秒）

    def __init__(self, agent_loop, on_explore_complete: Callable = None):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete
        self._last_activity: float = time.time()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._sop_content: Optional[str] = None
        self._iteration_count: int = 0  # Ralph Loop 迭代计数
        self._ralph_start_time: float = 0  # Ralph Loop 开始时间
        self._state_file: Path = SEED_DIR / "ralph_state.json"  # 状态持久化
        self._load_sop()

    def _load_sop(self):
        """加载自主探索 SOP"""
        if SOP_PATH.exists():
            with open(SOP_PATH, 'r', encoding='utf-8') as f:
                self._sop_content = f.read()
            logger.info(f"Loaded autonomous SOP from {SOP_PATH}")
        else:
            logger.warning(f"SOP file not found: {SOP_PATH}")

    def record_activity(self):
        """记录用户活动时间"""
        self._last_activity = time.time()

    def get_idle_time(self) -> float:
        """获取当前空闲时间（秒）"""
        return time.time() - self._last_activity

    async def start(self):
        """启动空闲监控"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._idle_monitor_loop())
        logger.info("Autonomous explorer started")

    async def stop(self):
        """停止空闲监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Autonomous explorer stopped")

    async def _idle_monitor_loop(self):
        """空闲监控循环"""
        while self._running:
            idle_time = self.get_idle_time()

            if idle_time >= self.IDLE_TIMEOUT:
                logger.info(f"Idle for {idle_time/60:.1f} minutes, starting autonomous exploration")
                await self._execute_autonomous_task()
                self.record_activity()  # 执行后重置计时

            # 每30秒检查一次
            await asyncio.sleep(30)

    # === Ralph Loop 增强方法 ===

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志（Ralph Loop 核心机制）"""
        if COMPLETION_PROMISE_FILE.exists():
            content = COMPLETION_PROMISE_FILE.read_text().strip()
            if content in COMPLETION_PROMISE_TOKENS:
                logger.info(f"Completion promise detected: {content}")
                # 清除标志
                COMPLETION_PROMISE_FILE.unlink()
                return True
        return False

    def _check_safety_limits(self) -> bool:
        """检查安全上限（防止无限循环）"""
        # 迭代上限
        if self._iteration_count >= RALPH_MAX_ITERATIONS:
            logger.warning(f"Ralph Loop exceeded max iterations ({RALPH_MAX_ITERATIONS})")
            return True

        # 时间上限
        if self._ralph_start_time > 0:
            elapsed = time.time() - self._ralph_start_time
            if elapsed >= RALPH_MAX_DURATION:
                logger.warning(f"Ralph Loop exceeded max duration ({RALPH_MAX_DURATION}s)")
                return True

        return False

    async def _reset_context_if_needed(self) -> Optional[str]:
        """条件性重置上下文（防止上下文漂移）"""
        if not CONTEXT_RESET_ENABLED:
            return None

        if self._iteration_count % CONTEXT_RESET_INTERVAL != 0:
            return None

        # 保存关键状态
        preserved = self._extract_critical_context()

        # 重置 history
        self.agent.history.clear()

        # 重新注入保留信息（如有）
        if preserved:
            self.agent.history.append({
                "role": "system",
                "content": f"[迭代 {self._iteration_count} 状态摘要]\n{preserved}"
            })

        logger.info(f"Context reset at iteration {self._iteration_count}")
        return preserved

    def _extract_critical_context(self) -> Optional[str]:
        """提取关键上下文（可选保留）"""
        # 从 agent.history 提取关键决策/发现
        if not self.agent.history:
            return None

        # 提取最后一条 assistant 消息的摘要
        for msg in reversed(self.agent.history):
            if msg.get("role") == "assistant" and msg.get("content"):
                return f"上次执行摘要: {msg['content'][:300]}"
        return None

    def _persist_state(self, response: str = ""):
        """持久化当前状态（支持进程恢复）"""
        SEED_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "iteration": self._iteration_count,
            "start_time": self._ralph_start_time,
            "last_response": response[:500] if response else "",
            "timestamp": time.time()
        }
        self._state_file.write_text(json.dumps(state, indent=2))

    def _load_or_init_state(self):
        """加载或初始化状态（支持进程恢复）"""
        if self._state_file.exists():
            try:
                state = json.loads(self._state_file.read_text())
                self._iteration_count = state.get("iteration", 0)
                self._ralph_start_time = state.get("start_time", time.time())
                logger.info(f"Resumed Ralph Loop from iteration {self._iteration_count}")
            except (json.JSONDecodeError, KeyError):
                self._iteration_count = 0
                self._ralph_start_time = time.time()
        else:
            self._iteration_count = 0
            self._ralph_start_time = time.time()

    def _cleanup_state(self):
        """清理状态文件"""
        if self._state_file.exists():
            self._state_file.unlink()

    async def _execute_autonomous_task(self):
        """执行自主探索任务（复用 Agent Loop + Ralph Loop 增强）"""
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return

        # 加载或初始化 Ralph Loop 状态
        self._load_or_init_state()

        # 构建自主探索 prompt（包含完整上下文）
        todo_path = SEED_DIR / "TODO.md"
        has_todo = todo_path.exists()
        todo_content = ""
        if has_todo:
            with open(todo_path, 'r', encoding='utf-8') as f:
                todo_content = f.read()

        # 构建完整 prompt
        prompt = self._build_autonomous_prompt(todo_content, has_todo)

        logger.info("Starting autonomous exploration via Agent Loop (Ralph enhanced)")

        # 保存原始 system prompt、history 和迭代限制，以便恢复
        original_system_prompt = self.agent.system_prompt
        original_history = list(self.agent.history)
        original_max_iterations = self.agent.max_iterations

        try:
            # 临时设置自主探索的 system prompt 和更高的迭代限制
            self.agent.system_prompt = prompt
            # 自主探索任务通常需要更多迭代（执行多个TODO、调用多个工具）
            self.agent.max_iterations = 100

            # Ralph Loop 增强循环
            while True:
                self._iteration_count += 1

                # 1. 安全检查
                if self._check_safety_limits():
                    logger.info("Ralph Loop safety limit reached, generating report")
                    break

                # 2. completion_promise 检测（外部完成验证）
                if self._check_completion_promise():
                    logger.info("Completion promise detected, exiting Ralph loop")
                    self._cleanup_state()
                    if self.on_explore_complete:
                        if asyncio.iscoroutinefunction(self.on_explore_complete):
                            await self.on_explore_complete("DONE")
                        else:
                            self.on_explore_complete("DONE")
                    return "DONE"

                # 3. 可选上下文重置
                await self._reset_context_if_needed()

                # 4. 执行一轮 Agent Loop
                response = await self.agent.run("继续执行自主探索任务")

                # 5. 持久化状态
                self._persist_state(response)

                # 6. 检查是否完成任务
                if response and "任务完成" in response or "已完成" in response:
                    logger.info(f"Autonomous exploration completed at iteration {self._iteration_count}")
                    self._cleanup_state()
                    break

                # 7. 空响应检测（可能需要重新注入 prompt）
                if not response:
                    logger.warning(f"Empty response at iteration {self._iteration_count}, re-injecting prompt")
                    # 重新注入任务 prompt
                    self.agent.history.append({"role": "user", "content": prompt})

                # 8. 短暂等待（防止过快循环）
                await asyncio.sleep(2)

            if response:
                logger.info(f"Autonomous exploration completed, response length: {len(response)}")
                if self.on_explore_complete:
                    if asyncio.iscoroutinefunction(self.on_explore_complete):
                        await self.on_explore_complete(response)
                    else:
                        self.on_explore_complete(response)
            else:
                logger.warning("Autonomous exploration returned empty response")

            return response

        except Exception as e:
            logger.exception(f"Autonomous exploration failed: {e}")
            # 保存状态以便恢复
            self._persist_state(str(e))
            return None
        finally:
            # 恢复原始 system prompt 和迭代限制
            self.agent.system_prompt = original_system_prompt
            self.agent.max_iterations = original_max_iterations
            # 注意：不恢复 history，因为 Ralph Loop 可能已重置

    def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
        """构建自主探索 prompt（包含完整 system prompt + skills + SOP + Memory Graph 选择）"""
        # 获取 agent 的 system prompt（已包含 skills）
        base_system_prompt = self.agent.system_prompt or ""

        # 获取 skills prompt（从 skill_loader）
        skills_prompt = ""
        best_skill_suggestion = ""
        if hasattr(self.agent, 'skill_loader') and self.agent.skill_loader:
            skills_prompt = self.agent.skill_loader.get_skills_prompt()

            # Memory Graph 增强：根据任务类型选择最佳 skill
            signals = self._extract_task_signals(todo_content, has_todo)
            best_skill = self.agent.skill_loader.select_best_skill(
                signals=signals,
                available_tools=self.agent.tools.get_tool_names() if hasattr(self.agent.tools, 'get_tool_names') else None
            )

            if best_skill:
                # 使用 Gene slice（Tier 2a）注入，而非完整 skill
                gene_slice = self.agent.skill_loader.get_gene_slice(best_skill)
                if gene_slice:
                    best_skill_suggestion = f"""## 推荐技能 (Memory Graph 选择)

基于历史成功率，推荐使用技能: **{best_skill}**

{gene_slice}

"""
                    logger.info(f"Memory Graph selected skill: {best_skill}")

        # 构建 SOP 内容
        sop_prompt = f"""## 自主探索 SOP

{self._sop_content}

"""

        # 构建任务指令
        task_prompt = self._build_task_instruction(todo_content, has_todo)

        # 组合完整 prompt
        parts = []
        if base_system_prompt:
            parts.append(base_system_prompt)
        if skills_prompt and skills_prompt not in base_system_prompt:
            parts.append(skills_prompt)
        if best_skill_suggestion:
            parts.append(best_skill_suggestion)
        parts.append(sop_prompt)
        parts.append(task_prompt)

        return "\n\n".join(parts)

    def _extract_task_signals(self, todo_content: str, has_todo: bool) -> List[str]:
        """从任务内容提取触发信号"""
        signals = []

        if has_todo and todo_content:
            # 从 TODO 内容提取关键词
            lines = todo_content.split('\n')
            for line in lines[:5]:
                # 提取 TODO 条目中的关键词
                if line.strip():
                    words = line.split()
                    signals.extend(words[:3])

        # 根据任务类型添加基础信号
        if has_todo:
            signals.append("execute")
            signals.append("task")
        else:
            signals.append("plan")
            signals.append("generate")

        return signals[:10]

    def _build_task_instruction(self, todo_content: str, has_todo: bool) -> str:
        """构建任务指令部分"""
        prompt_parts = [
            "# 自主探索任务触发",
            "",
            "当前空闲30分钟，开始执行自主任务。",
            "",
            "## 当前状态",
            f"- TODO状态: {'有待执行任务' if has_todo else '无TODO，进入规划模式'}",
            "",
        ]

        if has_todo and todo_content.strip():
            prompt_parts.extend([
                "## 当前TODO内容",
                todo_content,
                "",
                "请按照 SOP 执行流程，逐个完成 TODO 条目：",
                "1. 在 <thinking> 内推演执行逻辑",
                "2. 执行任务并记录到工作记忆",
                "3. 完成后标记 TODO 并更新工作记忆",
                "",
            ])
        else:
            prompt_parts.extend([
                "## 规划模式",
                "当前无TODO，请进入规划模式：",
                "1. 读取 history.md 和工作记忆",
                "2. 反思低价值操作，提炼进化线索",
                "3. 产出5-7条TODO（格式：`[ ] 类型 | 目标 | 验收标准 | 预期沉淀`）",
                "4. 更新 TODO.md 文件",
                "",
            ])

        prompt_parts.extend([
            "## SOP 核心原则",
            "- 价值公式：实际执行可落地性 × 进化沉淀价值",
            "- 不推诿、有逻辑、重沉淀",
            "- 失败升级：1次重试，2次探测，3次换方案",
            "- 不可逆操作需先确认用户（但自主模式下跳过需确认的操作）",
            "",
            "请开始执行自主探索任务。",
        ])

        return "\n".join(prompt_parts)


async def create_autonomous_explorer(agent_loop, on_explore_complete: Callable = None) -> AutonomousExplorer:
    """创建自主探索器"""
    explorer = AutonomousExplorer(agent_loop, on_explore_complete)
    await explorer.start()
    return explorer