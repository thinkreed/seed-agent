"""自主探索模块：空闲时根据 SOP 执行自主任务"""

import os
import asyncio
import time
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger("seed_agent")

# SOP 文档路径
SOP_PATH = Path(__file__).parent.parent / "auto" / "自主探索 SOP.md"
SEED_DIR = Path(__file__).parent.parent / ".seed"


class AutonomousExplorer:
    """自主探索执行器"""

    IDLE_TIMEOUT = 15 * 60  # 15分钟（秒）

    def __init__(self, agent_loop, on_explore_complete: Callable = None):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete
        self._last_activity: float = time.time()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._sop_content: Optional[str] = None
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

    async def _execute_autonomous_task(self):
        """执行自主探索任务"""
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return

        try:
            # 构建自主探索 prompt（包含完整上下文）
            todo_path = SEED_DIR / "TODO.md"

            # 检查是否有 TODO
            has_todo = todo_path.exists()
            todo_content = ""
            if has_todo:
                with open(todo_path, 'r', encoding='utf-8') as f:
                    todo_content = f.read()

            # 构建完整 prompt（注入 system prompt + skills + SOP）
            prompt = self._build_autonomous_prompt(todo_content, has_todo)

            # 执行自主任务（使用 gateway 直接调用，不依赖 agent history）
            logger.info("Executing autonomous exploration...")
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "开始执行自主探索任务"}
            ]

            response = await self.agent.gateway.chat(
                messages=messages,
                model=self.agent.model_id,
                tools=self.agent.tools.get_all_schemas()
            )

            # 回调完成通知
            if self.on_explore_complete:
                await self.on_explore_complete(response)

            logger.info(f"Autonomous exploration completed: {response[:200]}...")

        except Exception as e:
            logger.exception(f"Autonomous exploration failed: {e}")

    def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
        """构建自主探索 prompt（包含完整 system prompt + skills + SOP）"""
        # 获取 agent 的 system prompt（已包含 skills）
        base_system_prompt = self.agent.system_prompt or ""

        # 获取 skills prompt（从 skill_loader）
        skills_prompt = ""
        if hasattr(self.agent, 'skill_loader') and self.agent.skill_loader:
            skills_prompt = self.agent.skill_loader.get_skills_prompt()

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
        parts.append(sop_prompt)
        parts.append(task_prompt)

        return "\n\n".join(parts)

    def _build_task_instruction(self, todo_content: str, has_todo: bool) -> str:
        """构建任务指令部分"""
        prompt_parts = [
            "# 自主探索任务触发",
            "",
            "当前空闲15分钟，开始执行自主任务。",
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