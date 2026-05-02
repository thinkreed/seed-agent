"""
Subagent 机制 - 独立上下文的子代理执行器

核心特性:
- 独立 context window，不共享主对话历史
- 可配置权限集（read-only, review, implement, plan）
- 并行执行支持
- 结果聚合（只返回关键结果，不污染主上下文）

OpenTelemetry 嵌入:
- Span: seed.subagent.execute
- Attributes: type, task_id, status
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.client import LLMGateway

# OpenTelemetry 可观测性（自动处理 ImportError）
from src.observability import (
    SPAN_SUBAGENT_EXECUTE,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_subagent_span_attributes,
)
from src.tools import ToolRegistry
from src.tools.utils import parse_tool_arguments

_OBSERVABILITY_ENABLED = is_observability_enabled()

logger = logging.getLogger(__name__)


class SubagentType(Enum):
    """Subagent 类型枚举"""
    EXPLORE = "explore"      # 只读探索：搜索文件、阅读代码
    REVIEW = "review"       # 审查验证：只读 + 代码执行
    IMPLEMENT = "implement" # 实现执行：全权限
    PLAN = "plan"           # 规划分析：只读 + 记忆写入


def _get_subagent_type_key(subagent_type: SubagentType | str) -> str:
    """获取 SubagentType 的字符串键（用于字典查找）

    Args:
        subagent_type: SubagentType 枚举或字符串

    Returns:
        str: 类型键（"explore", "review", "implement", "plan"）
    """
    if isinstance(subagent_type, SubagentType):
        return subagent_type.value
    return subagent_type


# 使用共享配置模块
try:
    from src.shared_config import get_subagent_timeout_config
    _timeout_config = get_subagent_timeout_config()
    _default_timeouts = {
        "explore": _timeout_config.explore,
        "review": _timeout_config.review,
        "implement": _timeout_config.implement,
        "plan": _timeout_config.plan,
    }
    MAX_SUBAGENT_ITERATIONS = _timeout_config.max_iterations
except ImportError:
    # Fallback: 使用默认值
    _default_timeouts = {
        "explore": 180,
        "review": 600,
        "implement": 900,
        "plan": 300,
    }
    MAX_SUBAGENT_ITERATIONS = 15

# 导出为模块级常量
DEFAULT_TIMEOUTS: dict[str, int] = _default_timeouts


# 权限集定义
PERMISSION_SETS: dict[str, set[str]] = {
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
# 使用 .value 作为键以支持跨模块导入的枚举比较
SUBAGENT_TYPE_PERMISSIONS: dict[str, str] = {
    "explore": "read_only",
    "review": "review",
    "implement": "implement",
    "plan": "plan",
}

# Subagent 类型对应的 system prompt 模板
# 使用 .value 作为键以支持跨模块导入的枚举比较
SUBAGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "explore": """你是一个探索型子代理 (Explore Subagent)。

你的职责是：
- 搜索和分析代码文件
- 理解项目结构和代码逻辑
- 收集信息并汇报发现

限制：
- 你只能读取文件，不能修改任何内容
- 完成后提供简洁的发现摘要
- 不要输出冗长的原始文件内容，只输出关键发现""",

    "review": """你是一个审查型子代理 (Review Subagent)。

你的职责是：
- 审查代码质量和安全性
- 运行测试验证功能
- 检查代码规范和最佳实践

限制：
- 你只能读取文件和执行代码
- 不能修改任何文件
- 完成后提供结构化的审查报告""",

    "implement": """你是一个实现型子代理 (Implement Subagent)。

你的职责是：
- 实现功能代码
- 修复 bug
- 重构代码

能力：
- 完整的文件读写权限
- 代码执行能力
- 记忆系统访问

完成后提供简洁的实现总结。""",

    "plan": """你是一个规划型子代理 (Plan Subagent)。

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
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    iterations: int = 0
    parent_session_id: str | None = None


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
        model_id: str | None = None,
        max_iterations: int = MAX_SUBAGENT_ITERATIONS,
        timeout: int | None = None,
        custom_system_prompt: str | None = None,
        custom_tools: set[str] | None = None,
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
        self.timeout = timeout or DEFAULT_TIMEOUTS.get(_get_subagent_type_key(subagent_type), 300)

        # 独立的对话历史
        self.history: list[dict] = []

        # 工具注册
        self.tools = ToolRegistry()
        self._setup_tools(custom_tools)

        # System prompt
        base_prompt = SUBAGENT_SYSTEM_PROMPTS[_get_subagent_type_key(subagent_type)]
        self.system_prompt = custom_system_prompt or base_prompt

        # 状态
        self.state: SubagentState | None = None

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents["defaults"].defaults.primary

    def _setup_tools(self, custom_tools: set[str] | None = None):
        """设置工具集"""
        # 确定权限集
        type_key = _get_subagent_type_key(self.subagent_type)
        if custom_tools:
            allowed_tools = custom_tools
        else:
            permission_set_name = SUBAGENT_TYPE_PERMISSIONS[type_key]
            allowed_tools = PERMISSION_SETS[permission_set_name]

        self._allowed_tools = allowed_tools

        # 注册所有工具（后续会过滤）
        from src.tools.builtin_tools import register_builtin_tools
        from src.tools.memory_tools import register_memory_tools
        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)

        # 过滤工具
        self._filter_tools(allowed_tools)

    def _filter_tools(self, allowed: set[str]):
        """只保留允许的工具（一次性重建，避免逐个删除的低效操作）"""
        # 一次性重建字典，只保留允许的工具
        self.tools._tools = {
            name: tool for name, tool in self.tools._tools.items()
            if name in allowed
        }
        self.tools._tool_schemas = {
            name: schema for name, schema in self.tools._tool_schemas.items()
            if name in allowed
        }

    def _build_messages(self) -> list[dict]:
        """构建消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        return messages

    async def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """执行工具调用"""
        results = []
        for tool_call in tool_calls:
            tool_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = parse_tool_arguments(tool_call["function"]["arguments"])

            try:
                result = await self.tools.execute(tool_name, **tool_args)
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": str(result)
                })
            except Exception as e:
                error_type = type(e).__name__
                full_error_msg = str(e)  # 保留完整错误信息
                truncated_msg = full_error_msg[:200]  # 截断用于返回给 LLM
                # 记录完整错误到日志（便于调试）
                logger.error(f"Tool {tool_name} failed: {error_type}: {full_error_msg}")
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": f"Error in {tool_name}: {error_type} - {truncated_msg}"
                })

        return results

    async def run(self, prompt: str, task_id: str | None = None) -> SubagentState:
        """
        执行 Subagent 任务

        Args:
            prompt: 任务提示
            task_id: 任务 ID（可选，用于状态跟踪）

        Returns:
            SubagentState: 执行状态

        OpenTelemetry 嵌入点:
        - Span: seed.subagent.execute
        - Attributes: type, task_id, status
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

        # OpenTelemetry Span 创建
        tracer = get_tracer()
        span = None
        start_time = time.time()

        if tracer and _OBSERVABILITY_ENABLED:
            span = tracer.start_span(SPAN_SUBAGENT_EXECUTE)
            set_subagent_span_attributes(
                span,
                subagent_type=self.subagent_type.value,
                task_id=task_id,
                status="running"
            )

        try:
            # 超时执行
            result = await asyncio.wait_for(
                self._run_loop(),
                timeout=self.timeout
            )
            self.state.status = "completed"
            self.state.result = result

            # 记录成功
            if span:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("seed.subagent.status", "completed")
                span.set_attribute("seed.subagent.duration_ms", duration_ms)
                span.set_status(StatusCode.OK)

        except asyncio.TimeoutError:
            logger.warning(f"Subagent {task_id} timed out after {self.timeout}s")
            self.state.status = "timeout"
            self.state.error = f"Execution timed out after {self.timeout} seconds"

            # 记录超时
            if span:
                span.set_attribute("seed.subagent.status", "timeout")
                span.set_attribute("seed.error.message", self.state.error)
                span.set_status(StatusCode.ERROR)

        except Exception as e:
            logger.error(f"Subagent {task_id} failed: {e}")
            self.state.status = "failed"
            self.state.error = str(e)

            # 记录失败
            if span:
                span.record_exception(e)
                span.set_attribute("seed.subagent.status", "failed")
                span.set_attribute("seed.error.message", str(e)[:500])
                span.set_status(StatusCode.ERROR, str(e)[:200])

        finally:
            self.state.completed_at = datetime.now()
            if span:
                span.end()

        return self.state

    async def _run_loop(self) -> str:
        """主执行循环"""
        # 确保 state 已初始化（由 run() 方法设置）
        if self.state is None:
            raise RuntimeError("SubagentState must be initialized before _run_loop. Call run() first.")

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

            choice = response["choices"][0]
            message = choice["message"]
            self.history.append(message)

            if message.get("tool_calls"):
                tool_results = await self._execute_tool_calls(message["tool_calls"])
                self.history.extend(tool_results)
            else:
                # 无工具调用 = 完成
                return message.get("content", "")

        raise RuntimeError(f"Subagent exceeded maximum iterations ({self.max_iterations})")


class SubagentResult:
    """Subagent 执行结果"""

    def __init__(self, state: SubagentState):
        self.state = state

    @property
    def success(self) -> bool:
        return self.state.status == "completed"

    @property
    def result(self) -> str | None:
        return self.state.result

    @property
    def error(self) -> str | None:
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

    def to_dict(self) -> dict:
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
