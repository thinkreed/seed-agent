"""
Ask User 数据类型定义

基于 qwen-code askUserQuestion.ts 设计：
- 问题类型枚举（单选、多选、文本输入、确认）
- 选项定义（label、value、description）
- 用户响应结构
- 完整请求/结果数据结构

核心特性：
- 结构化问题定义
- 多选支持
- 自定义输入支持
- 取消/超时状态

参考：
- qwen-code: askUserQuestion.ts
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class QuestionType(Enum):
    """问题类型枚举"""

    SINGLE_SELECT = "single_select"  # 单选
    MULTI_SELECT = "multi_select"  # 多选
    TEXT_INPUT = "text_input"  # 文本输入
    CONFIRMATION = "confirmation"  # 确认（是/否）


@dataclass
class QuestionOption:
    """选项定义

    Attributes:
        label: 选项显示文本
        value: 选项值（默认等于 label）
        description: 选项描述（可选）
    """

    label: str
    value: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self):
        """确保 value 有默认值"""
        if self.value is None:
            self.value = self.label

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {"label": self.label, "value": self.value}
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class Question:
    """问题定义

    Attributes:
        question: 问题文本
        header: 简短标题（<=30字符，用于 UI 显示）
        options: 选项列表（2-4个）
        question_type: 问题类型
        multi_select: 是否多选
        allow_custom: 是否允许自定义输入
        default: 默认选项值
    """

    question: str
    header: str
    options: list[QuestionOption] = field(default_factory=list)
    question_type: QuestionType = QuestionType.SINGLE_SELECT
    multi_select: bool = False
    allow_custom: bool = True
    default: Optional[str] = None

    def __post_init__(self):
        """验证问题结构"""
        # 截断 header 到 30 字符
        if len(self.header) > 30:
            self.header = self.header[:30]

        # 验证选项数量（2-4个）
        if self.options and not (2 <= len(self.options) <= 4):
            # 自动调整：不足2个添加默认，超过4个截断
            if len(self.options) < 2:
                self.options.extend(
                    [QuestionOption(label="Yes"), QuestionOption(label="No")]
                )
            elif len(self.options) > 4:
                self.options = self.options[:4]

        # 根据 multi_select 设置 question_type
        if self.multi_select:
            self.question_type = QuestionType.MULTI_SELECT

        # 确认类型自动设置选项
        if self.question_type == QuestionType.CONFIRMATION and not self.options:
            self.options = [
                QuestionOption(label="Yes", value="yes"),
                QuestionOption(label="No", value="no"),
            ]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "question": self.question,
            "header": self.header,
            "options": [opt.to_dict() for opt in self.options],
            "question_type": self.question_type.value,
            "multi_select": self.multi_select,
            "allow_custom": self.allow_custom,
            "default": self.default,
        }


@dataclass
class UserResponse:
    """用户响应

    Attributes:
        question_id: 问题 ID（索引）
        selected: 选中的选项值列表
        custom_input: 自定义输入内容
    """

    question_id: str
    selected: list[str] = field(default_factory=list)
    custom_input: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {
            "question_id": self.question_id,
            "selected": self.selected,
        }
        if self.custom_input:
            result["custom_input"] = self.custom_input
        return result


@dataclass
class AskUserRequest:
    """Ask User 请求

    完整的用户交互请求结构

    Attributes:
        questions: 问题列表
        session_id: 会话 ID
        request_id: 请求唯一 ID
        created_at: 创建时间戳
        metadata: 额外元数据
    """

    questions: list[Question]
    session_id: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "questions": [q.to_dict() for q in self.questions],
            "session_id": self.session_id,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_simple(
        cls,
        question: str,
        options: Optional[list[str]] = None,
        header: Optional[str] = None,
        session_id: str = "",
        multi_select: bool = False,
    ) -> AskUserRequest:
        """从简单参数创建请求

        Args:
            question: 问题文本
            options: 选项列表（可选）
            header: 简短标题（可选）
            session_id: 会话 ID
            multi_select: 是否多选

        Returns:
            AskUserRequest 实例
        """
        # 构造选项
        if options:
            q_options = [QuestionOption(label=o) for o in options]
        else:
            q_options = [QuestionOption(label="Yes"), QuestionOption(label="No")]

        # 构造问题
        q = Question(
            question=question,
            header=header or question[:30],
            options=q_options,
            multi_select=multi_select,
        )

        return cls(questions=[q], session_id=session_id)


@dataclass
class AskUserResult:
    """Ask User 结果

    用户交互的结果结构

    Attributes:
        request_id: 对应的请求 ID
        responses: 用户响应列表
        cancelled: 用户取消
        timeout: 超时
    """

    request_id: str
    responses: list[UserResponse] = field(default_factory=list)
    cancelled: bool = False
    timeout: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "responses": [r.to_dict() for r in self.responses],
            "cancelled": self.cancelled,
            "timeout": self.timeout,
        }

    @classmethod
    def cancelled_result(cls, request_id: str) -> AskUserResult:
        """创建取消结果

        Args:
            request_id: 对应的请求 ID

        Returns:
            取消状态的 AskUserResult
        """
        return cls(request_id=request_id, cancelled=True)

    @classmethod
    def timeout_result(cls, request_id: str) -> AskUserResult:
        """创建超时结果

        Args:
            request_id: 对应的请求 ID

        Returns:
            超时状态的 AskUserResult
        """
        return cls(request_id=request_id, timeout=True)

    def get_selected_values(self) -> list[str]:
        """获取所有选中的值

        Returns:
            所有响应中选中值的列表
        """
        values = []
        for response in self.responses:
            values.extend(response.selected)
        return values

    def get_first_selected(self) -> Optional[str]:
        """获取第一个选中的值

        Returns:
            第一个选中值，或 None
        """
        if self.responses and self.responses[0].selected:
            return self.responses[0].selected[0]
        return None


@dataclass
class AskUserState:
    """Ask User 状态管理

    用于跟踪当前的 ask_user 等待状态

    Attributes:
        pending_request: 当前等待中的请求
        waiting_event: asyncio.Event 用于等待响应
        response: 用户响应（注入后设置）
    """

    pending_request: Optional[AskUserRequest] = None
    waiting_event: asyncio.Event = field(default_factory=asyncio.Event)
    response: Optional[AskUserResult] = None

    def set_request(self, request: AskUserRequest) -> None:
        """设置等待请求

        Args:
            request: Ask User 请求
        """
        self.pending_request = request
        self.response = None
        self.waiting_event.clear()

    def inject_response(self, response: AskUserResult) -> None:
        """注入用户响应

        Args:
            response: 用户响应结果
        """
        self.response = response
        self.pending_request = None
        self.waiting_event.set()

    def clear(self) -> None:
        """清理状态"""
        self.pending_request = None
        self.response = None
        self.waiting_event.clear()

    def is_waiting(self) -> bool:
        """是否正在等待"""
        return self.pending_request is not None


# 全局状态管理器（单例）
_global_ask_user_state: Optional[AskUserState] = None


def get_ask_user_state() -> AskUserState:
    """获取全局 Ask User 状态管理器"""
    global _global_ask_user_state
    if _global_ask_user_state is None:
        _global_ask_user_state = AskUserState()
    return _global_ask_user_state


def reset_ask_user_state() -> None:
    """重置全局状态管理器"""
    global _global_ask_user_state
    if _global_ask_user_state:
        _global_ask_user_state.clear()
    _global_ask_user_state = AskUserState()
