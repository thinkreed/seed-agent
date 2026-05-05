"""
请求和响应定义

包含：
- UserResponse: 用户响应
- AskUserRequest: Ask User 请求

核心特性：
- 多问题支持
- 自定义输入支持
- 简易创建方法
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ._types import Question, QuestionOption


@dataclass
class UserResponse:
    """用户响应"""

    question_id: str
    selected: list[str] = field(default_factory=list)
    custom_input: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"question_id": self.question_id, "selected": self.selected}
        if self.custom_input:
            result["custom_input"] = self.custom_input
        return result


@dataclass
class AskUserRequest:
    """Ask User 请求"""

    questions: list[Question]
    session_id: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
        options: list[str] | None = None,
        header: str | None = None,
        session_id: str = "",
        multi_select: bool = False,
    ) -> AskUserRequest:
        """从简单参数创建请求"""
        if options:
            q_options = [QuestionOption(label=o) for o in options]
        else:
            q_options = [QuestionOption(label="Yes"), QuestionOption(label="No")]

        q = Question(
            question=question,
            header=header or question[:30],
            options=q_options,
            multi_select=multi_select,
        )

        return cls(questions=[q], session_id=session_id)


__all__ = ["UserResponse", "AskUserRequest"]