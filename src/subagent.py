"""
Subagent 机制 - 独立上下文的子代理执行器

核心特性:
- 独立 context window，不共享主对话历史
- 可配置权限集（read-only, review, implement, plan）
- 并行执行支持
- 结果聚合（只返回关键结果，不污染主上下文）
"""

import asyncio
import uuid
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging

from client import LLMGateway
from tools import ToolRegistry

logger = logging.getLogger(__name__)


class SubagentType(Enum):
    """Subagent 类型枚举"""
    EXPLORE = "explore"      # 只读探索：搜索文件、阅读代码
    REVIEW = "review"       # 审查验证：只读 + 代码执行
    IMPLEMENT = "implement" # 实现执行：全权限
    PLAN = "plan"           # 规划分析：只读 + 记忆写入

# 不同类型任务的默认超时时间（秒）
# EXPLORE: 快速查询 (3m)
# REVIEW: 审查+测试 (10m)
# IMPLEMENT: 实现+调试 (15m)
# PLAN: 规划分析 (5m)
DEFAULT_TIMEOUTS: Dict[SubagentType, int] = {
    SubagentType.EXPLORE: 180,
    SubagentType.REVIEW: 600,
    SubagentType.IMPLEMENT: 900,
    SubagentType.PLAN: 300,
}


# 权限集定义
PERMISSION_SETS: Dict[str, Set[str]] = {
    "read_only": {
        "file_read",
        "search_history",
        "ask_user",
    },
    "review": {
        "file_read",
        "code_as_policy",
        "search_history",
        "ask_user",
    },
    "implement": {
        "file_read",
        "file_write",
        "file_edit",
        "code_as_policy",
        "write_memory",
        "read_memory_index",
        "search_memory",
        "search_history",
        "ask_user",
        "run_diagnosis",
    },
    "plan": {
        "file_read",
        "write_memory",
        "read_memory_index",
        "search_memory",
        "search_history",
        "ask_user",
    },
}

# Subagent 类型对应的默认权限集
SUBAGENT_TYPE_PERMISSIONS: Dict[SubagentType, str] = {
    SubagentType.EXPLORE: "read_only",
    SubagentType.REVIEW: "review",
    SubagentType.IMPLEMENT: "implement",
    SubagentType.PLAN: "plan",
}

# Subagent 类型对应的 system prompt 模板
SUBAGENT_SYSTEM_PROMPTS: Dict[SubagentType, str] = {
    SubagentType.EXPLORE: """你是一个探索型子代理 (Explore Subagent)。

你的职责是：
- 搜索和分析代码文件
- 理解项目结构和代码逻辑
- 收集信息并汇报发现

限制：
- 你只能读取文件，不能修改任何内容
- 完成后提供简洁的发现摘要
- 不要输出冗长的原始文件内容，只输出关键发现""",

    SubagentType.REVIEW: """你是一个审查型子代理 (Review Subagent)。

你的职责是：
- 审查代码质量和安全性
- 运行测试验证功能
- 检查代码规范和最佳实践

限制：
- 你只能读取文件和执行代码
- 不能修改任何文件
- 完成后提供结构化的审查报告""",

    SubagentType.IMPLEMENT: """你是一个实现型子代理 (Implement Subagent)。

你的职责是：
- 实现功能代码
- 修复 bug
- 重构代码

能力：
- 完整的文件读写权限
- 代码执行能力
- 记忆系统访问

完成后提供简洁的实现总结。""",

    SubagentType.PLAN: """你是一个规划型子代理 (Plan Subagent)。

你的职责是：
- 分析任务需求
- 制定执行计划
- 记录关键决策到记忆系统

限制：
- 你只能读取文件和写入记忆
- 不能修改代码文件
- 完成后提供结构化的执行计划""",
}


@dataclass
class SubagentState:
    """Subagent 状态"""
    id: str
    subagent_type: SubagentType
    status: str  # "pending", "running", "completed", "failed", "timeout"
    prompt: str
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    iterations: int = 0
    parent_session_id: Optional[str] = None


class SubagentInstance:
    """
    独立上下文的 Subagent 执行实例

    每个实例有独立的:
    - 对话历史 (history)
    - 工具集 (filtered tools)
    - 执行状态
    """

    MAX_SUBAGENT_ITERATIONS = 15  # Subagent 默认迭代上限较低

    def __init__(
        self,
        gateway: LLMGateway,
        subagent_type: SubagentType,
        model_id: Optional[str] = None,
        max_iterations: int = MAX_SUBAGENT_ITERATIONS,
        timeout: Optional[int] = None,
        custom_system_prompt: Optional[str] = None,
        custom_tools: Optional[Set[str]] = None,
    ):
        """
        初始化 Subagent 实例

        Args:
            gateway: LLM 网关实例（复用父 agent 的）
            subagent_type: Subagent 类型
            model_id: 模型 ID（默认使用主模型）
            max_iterations: 最大迭代次数
            timeout: 超时时间（秒），默认根据任务类型动态设置
            custom_system_prompt: 自定义 system prompt
            custom_tools: 自定义工具集（覆盖默认权限集）
        """
        self.gateway = gateway
        self.subagent_type = subagent_type
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.timeout = timeout or DEFAULT_TIMEOUTS.get(subagent_type, 300)

        # 独立的对话历史
        self.history: List[Dict] = []

        # 工具注册
        self.tools = ToolRegistry()
        self._setup_tools(custom_tools)

        # System prompt
        base_prompt = SUBAGENT_SYSTEM_PROMPTS[subagent_type]
        self.system_prompt = custom_system_prompt or base_prompt

        # 状态
        self.state: Optional[SubagentState] = None

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents['defaults'].defaults.primary

    def _setup_tools(self, custom_tools: Optional[Set[str]] = None):
        """设置工具集"""
        # 确定权限集
        if custom_tools:
            allowed_tools = custom_tools
        else:
            permission_set_name = SUBAGENT_TYPE_PERMISSIONS[self.subagent_type]
            allowed_tools = PERMISSION_SETS[permission_set_name]

        self._allowed_tools = allowed_tools

        # 注册所有工具（后续会过滤）
        from tools.builtin_tools import register_builtin_tools
        from tools.memory_tools import register_memory_tools
        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)

        # 过滤工具
        self._filter_tools(allowed_tools)

    def _filter_tools(self, allowed: Set[str]):
        """只保留允许的工具"""
        tools_to_remove = [
            name for name in list(self.tools._tools.keys())
            if name not in allowed
        ]
        for name in tools_to_remove:
            del self.tools._tools[name]
            if name in self.tools._tool_schemas:
                del self.tools._tool_schemas[name]

    def _build_messages(self) -> List[Dict]:
        """构建消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        return messages

    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """执行工具调用"""
        results = []
        for tool_call in tool_calls:
            tool_id = tool_call['id']
            tool_name = tool_call['function']['name']
            raw_args = tool_call['function']['arguments']

            import json
            try:
                if isinstance(raw_args, str):
                    raw_args = raw_args.strip()
                    tool_args = json.loads(raw_args) if raw_args else {}
                else:
                    tool_args = raw_args if raw_args else {}
                if not isinstance(tool_args, dict):
                    tool_args = {}
            except (json.JSONDecodeError, TypeError, ValueError):
                tool_args = {}

            try:
                result = await self.tools.execute(tool_name, **tool_args)
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": str(result)
                })
            except Exception as e:
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": f"Error: {str(e)}"
                })

        return results

    async def run(self, prompt: str, task_id: Optional[str] = None) -> SubagentState:
        """
        执行 Subagent 任务

        Args:
            prompt: 任务提示
            task_id: 任务 ID（可选，用于状态跟踪）

        Returns:
            SubagentState: 执行状态
        """
        task_id = task_id or str(uuid.uuid4())[:8]
        self.state = SubagentState(
            id=task_id,
            subagent_type=self.subagent_type,
            status="pending",
            prompt=prompt,
        )
        self.state.started_at = datetime.now()
        self.state.status = "running"

        self.history.append({"role": "user", "content": prompt})

        try:
            # 超时执行
            result = await asyncio.wait_for(
                self._run_loop(),
                timeout=self.timeout
            )
            self.state.status = "completed"
            self.state.result = result

        except asyncio.TimeoutError:
            logger.warning(f"Subagent {task_id} timed out after {self.timeout}s")
            self.state.status = "timeout"
            self.state.error = f"Execution timed out after {self.timeout} seconds"

        except Exception as e:
            logger.error(f"Subagent {task_id} failed: {e}")
            self.state.status = "failed"
            self.state.error = str(e)

        finally:
            self.state.completed_at = datetime.now()

        return self.state

    async def _run_loop(self) -> str:
        """主执行循环"""
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            self.state.iterations = iteration

            messages = self._build_messages()
            response = await self.gateway.chat_completion(
                self.model_id,
                messages,
                tools=self.tools.get_schemas()
            )

            choice = response['choices'][0]
            message = choice['message']
            self.history.append(message)

            if message.get('tool_calls'):
                tool_results = await self._execute_tool_calls(message['tool_calls'])
                self.history.extend(tool_results)
            else:
                # 无工具调用 = 完成
                return message.get('content', '')

        raise RuntimeError(f"Subagent exceeded maximum iterations ({self.max_iterations})")


class SubagentResult:
    """Subagent 执行结果"""

    def __init__(self, state: SubagentState):
        self.state = state

    @property
    def success(self) -> bool:
        return self.state.status == "completed"

    @property
    def result(self) -> Optional[str]:
        return self.state.result

    @property
    def error(self) -> Optional[str]:
        return self.state.error

    @property
    def summary(self) -> str:
        """返回结果摘要"""
        if self.success:
            # 截断过长的结果
            r = self.result or ""
            if len(r) > 500:
                return r[:500] + "...(truncated)"
            return r
        return f"[{self.state.status.upper()}] {self.error}"

    def to_dict(self) -> Dict:
        return {
            "id": self.state.id,
            "type": self.state.subagent_type.value,
            "status": self.state.status,
            "result": self.result,
            "error": self.error,
            "iterations": self.state.iterations,
            "duration": (
                (self.state.completed_at - self.state.started_at).total_seconds()
                if self.state.completed_at and self.state.started_at else None
            ),
        }