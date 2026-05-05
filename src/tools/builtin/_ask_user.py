"""
Ask User 机制

基于 qwen-code AskUserQuestion 工具设计：
- 真正的等待机制（而非字符串标记）
- 结构化问题定义
- 支持单选、多选、自定义输入

核心功能：
- ask_user: 发起用户交互
- AskUserRequest/AskUserResult: 数据类型
"""

import logging
from typing import Any

try:
    # 尝试从 src.tools 导入（正式运行时）
    from src.tools.ask_user_types import (
        AskUserRequest,
        AskUserResult,
        Question,
        QuestionOption,
        get_ask_user_state,
    )
except ImportError:
    # 回退到 tools 导入（测试时）
    from tools.ask_user_types import (
        AskUserRequest,
        AskUserResult,
        Question,
        QuestionOption,
        get_ask_user_state,
    )

logger = logging.getLogger("seed_agent.ask_user")


def ask_user(
    question: str,
    options: list[str] | None = None,
    header: str | None = None,
    multi_select: bool = False,
) -> str:
    """
    Ask user for input/confirmation during task execution.

    这是真正的等待机制：
    - 返回等待标记字符串
    - Harness 检测标记后暂停循环
    - 外部注入用户响应
    - Harness 恢复循环继续执行

    Args:
        question: 问题内容
        options: 选项列表（可选）
        header: 问题标题（可选）
        multi_select: 是否允许多选

    Returns:
        等待标记字符串（包含 AskUserRequest JSON）
    """
    # 构建选项
    if options:
        q_options = [QuestionOption(label=opt) for opt in options]
    else:
        q_options = [QuestionOption(label="Yes"), QuestionOption(label="No")]

    # 构建问题
    q = Question(
        question=question,
        header=header or question[:30],
        options=q_options,
        multi_select=multi_select,
    )

    # 构建请求
    request = AskUserRequest(questions=[q])

    # 获取状态并设置等待
    state = get_ask_user_state()
    state.set_request(request)

    logger.info(f"Ask user: {question[:50]}... (options: {len(options or [])})")

    # 返回等待标记
    return f"[AWAITING_USER_INPUT]\n{request.to_dict()}"


def process_user_response(response: AskUserResult) -> str:
    """处理用户响应

    Args:
        response: 用户响应结果

    Returns:
        处理后的内容字符串
    """
    state = get_ask_user_state()

    if state.is_waiting():
        state.set_response(response)
        logger.info(f"User response received: {response.responses}")

        # 构建响应内容
        results = []
        for resp in response.responses:
            if resp.selected:
                results.append(f"Selected: {resp.selected}")
            if resp.text:
                results.append(f"Input: {resp.text}")

        return "\n".join(results) if results else "User cancelled"

    return "Error: Not in waiting state"


def check_user_waiting() -> bool:
    """检查是否正在等待用户输入"""
    return get_ask_user_state().is_waiting()


def get_pending_request() -> AskUserRequest | None:
    """获取待处理的请求"""
    return get_ask_user_state().get_pending_request()