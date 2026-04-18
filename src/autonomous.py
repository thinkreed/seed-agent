"""自主探索模块：空闲时根据 SOP 执行自主任务"""

import os
import asyncio
import time
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger("seed_agent")

# 项目根目录（当前文件所在目录的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
# SOP 文档路径
SOP_PATH = PROJECT_ROOT / "auto" / "自主探索 SOP.md"
SEED_DIR = Path(os.path.expanduser("~")) / ".seed"


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
        """执行自主探索任务（带工具调用迭代循环 + 容错重试）"""
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return

        max_iterations = 20  # 防止无限循环
        max_consecutive_failures = 3  # 连续失败次数上限

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

        # 初始化消息历史
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "开始执行自主探索任务"}
        ]

        consecutive_failures = 0

        # 工具调用迭代循环
        for iteration in range(max_iterations):
            logger.info(f"Autonomous iteration {iteration + 1}/{max_iterations}")

            try:
                # 调用 LLM（带重试）
                response = await self._call_llm_with_retry(
                    messages, max_retries=3
                )

                if response is None:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"Consecutive LLM failures reached {max_consecutive_failures}, stopping")
                        break
                    continue

                # 重置连续失败计数
                consecutive_failures = 0

                # 提取响应内容
                choices = response.get("choices", [])
                if not choices:
                    logger.warning("LLM returned no choices, ending exploration")
                    break

                message = choices[0].get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])

                # 将助手消息加入历史
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                # 如果没有工具调用，说明任务完成
                if not tool_calls:
                    logger.info(f"Autonomous exploration completed (no more tool calls)")
                    if self.on_explore_complete:
                        if asyncio.iscoroutinefunction(self.on_explore_complete):
                            await self.on_explore_complete(content or "探索完成")
                        else:
                            self.on_explore_complete(content or "探索完成")
                    break

                # 执行工具调用
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    func = tc.get("function", {})
                    func_name = func.get("name", "")
                    func_args_str = func.get("arguments", "{}")

                    try:
                        import json
                        func_args = json.loads(func_args_str) if func_args_str else {}
                    except json.JSONDecodeError:
                        func_args = {}

                    try:
                        tool_result = await self.agent.tools.execute(func_name, **func_args)
                        # 确保结果是字符串
                        if not isinstance(tool_result, str):
                            tool_result = str(tool_result)
                    except Exception as tool_e:
                        logger.exception(f"Tool execution failed: {func_name}")
                        tool_result = f"Error executing {func_name}: {str(tool_e)}"

                    # 将工具结果加入历史
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": func_name,
                        "content": tool_result
                    })

                    logger.info(f"Executed tool: {func_name}, result length: {len(tool_result)}")

            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Iteration {iteration + 1} failed (consecutive: {consecutive_failures}): {e}")
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"Consecutive failures reached {max_consecutive_failures}, stopping exploration")
                    break
                # 继续下一轮迭代
                continue

        else:
            # 达到最大迭代次数
            logger.warning(f"Autonomous exploration hit max iterations ({max_iterations})")

        # 尝试获取最终总结（即使因失败中断也尝试）
        try:
            if len(messages) > 2:
                summary_prompt = messages + [{"role": "user", "content": "请用一段话总结你完成的工作和发现。如果探索被中断，请说明已完成的进度。"}]
                summary_response = await self._call_llm_with_retry(
                    summary_prompt[-5:], max_retries=2
                )
                if summary_response:
                    summary_choices = summary_response.get("choices", [])
                    if summary_choices:
                        summary_text = summary_choices[0].get("message", {}).get("content", "")
                        if self.on_explore_complete:
                            if asyncio.iscoroutinefunction(self.on_explore_complete):
                                await self.on_explore_complete(summary_text)
                            else:
                                self.on_explore_complete(summary_text)
        except Exception as e:
            logger.error(f"Failed to get summary: {e}")

    async def _call_llm_with_retry(self, messages: list, max_retries: int = 3) -> Optional[dict]:
        """带重试的 LLM 调用"""
        import asyncio
        for attempt in range(max_retries):
            try:
                response = await self.agent.gateway.chat_completion(
                    model_id=self.agent.model_id,
                    messages=messages,
                    tools=self.agent.tools.get_schemas()
                )
                return response
            except Exception as e:
                wait_time = 2 ** attempt  # 指数退避: 2s, 4s, 8s
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
        logger.error(f"LLM call failed after {max_retries} retries")
        return None

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