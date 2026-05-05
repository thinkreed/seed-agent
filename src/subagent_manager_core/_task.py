"""
SubagentManager - 任务定义模块

包含:
- SubagentTask dataclass
- 类型安全验证
- 辅助转换函数
"""

import logging
import uuid
from dataclasses import dataclass

from src.subagent import (
    DEFAULT_TIMEOUTS,
    SubagentType,
)

logger = logging.getLogger(__name__)


def _safe_int(
    value: str | float | None, default: int | None = None, min_val: int = 1
) -> int | None:
    """安全转换整数（用于 dataclass __post_init__）

    Args:
        value: 要转换的值（可能是 str, int, float, None 等）
        default: 转换失败时的默认值
        min_val: 最小有效值

    Returns:
        int | None: 转换后的整数，或默认值
    """
    if value is None:
        return default
    try:
        result = int(value) if isinstance(value, str) else int(value)
        if result < min_val:
            logger.warning(
                f"Converted value {result} < min_val {min_val}, using default {default}"
            )
            return default
        return result
    except (ValueError, TypeError) as e:
        logger.warning(
            f"Failed to convert '{value}' to int: {type(e).__name__}, using default {default}"
        )
        return default


@dataclass
class SubagentTask:
    """Subagent 任务定义

    类型安全: __post_init__ 确保数值参数为整数类型
    """

    id: str
    subagent_type: SubagentType
    prompt: str
    custom_tools: set[str] | None = None
    custom_system_prompt: str | None = None
    max_iterations: int | None = None
    timeout: int | None = None
    priority: int = 0  # 优先级，数值越高越先执行

    def __post_init__(self):
        """创建后类型验证和转换

        处理 LLM 返回字符串类型数值参数的情况：
        - LLM 可能返回 "timeout": "300" (JSON 字符串)
        - asyncio.wait_for 内部会执行 timeout <= 0 比较
        - 字符串与整数比较会导致 TypeError
        """
        # timeout 转换
        if self.timeout is not None:
            self.timeout = _safe_int(self.timeout, default=None, min_val=1)

        # max_iterations 转换
        if self.max_iterations is not None:
            converted = _safe_int(self.max_iterations, default=None, min_val=1)
            self.max_iterations = converted

        # priority 转换
        self.priority = _safe_int(self.priority, default=0, min_val=0)


def create_task(
    subagent_type: SubagentType,
    prompt: str,
    custom_tools: set[str] | None = None,
    custom_system_prompt: str | None = None,
    max_iterations: int | None = None,
    timeout: int | None = None,
    priority: int = 0,
) -> SubagentTask:
    """创建 SubagentTask 实例

    Args:
        subagent_type: Subagent 类型
        prompt: 任务提示
        custom_tools: 自定义工具集
        custom_system_prompt: 自定义 system prompt
        max_iterations: 最大迭代次数
        timeout: 超时时间（秒）
        priority: 优先级

    Returns:
        SubagentTask
    """
    task_id = str(uuid.uuid4())[:8]
    return SubagentTask(
        id=task_id,
        subagent_type=subagent_type,
        prompt=prompt,
        custom_tools=custom_tools,
        custom_system_prompt=custom_system_prompt,
        max_iterations=max_iterations,
        timeout=timeout,
        priority=priority,
    )


def get_default_timeout(subagent_type: SubagentType) -> int:
    """获取默认超时时间"""
    return DEFAULT_TIMEOUTS.get(subagent_type.value, 300)