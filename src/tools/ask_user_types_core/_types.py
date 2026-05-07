"""
问题类型和选项定义

包含：
- QuestionType: 问题类型枚举
- QuestionOption: 选项定义
- Question: 问题定义

核心特性：
- 单选/多选/文本输入/确认
- 选项描述支持
- 自动验证和调整
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QuestionType(Enum):
    """问题类型枚举"""

    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    TEXT_INPUT = "text_input"
    CONFIRMATION = "confirmation"


@dataclass
class QuestionOption:
    """选项定义"""

    label: str
    value: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if self.value is None:
            self.value = self.label

    def to_dict(self) -> dict[str, Any]:
        result = {"label": self.label, "value": self.value}
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class Question:
    """问题定义"""

    question: str
    header: str
    options: list[QuestionOption] = field(default_factory=list)
    question_type: QuestionType = QuestionType.SINGLE_SELECT
    multi_select: bool = False
    allow_custom: bool = True
    default: str | None = None

    def __post_init__(self) -> None:
        if len(self.header) > 30:
            self.header = self.header[:30]

        if self.options and not (2 <= len(self.options) <= 4):
            if len(self.options) < 2:
                self.options.extend([QuestionOption(label="Yes"), QuestionOption(label="No")])
            elif len(self.options) > 4:
                self.options = self.options[:4]

        if self.multi_select:
            self.question_type = QuestionType.MULTI_SELECT

        if self.question_type == QuestionType.CONFIRMATION and not self.options:
            self.options = [
                QuestionOption(label="Yes", value="yes"),
                QuestionOption(label="No", value="no"),
            ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "header": self.header,
            "options": [opt.to_dict() for opt in self.options],
            "question_type": self.question_type.value,
            "multi_select": self.multi_select,
            "allow_custom": self.allow_custom,
            "default": self.default,
        }


__all__ = ["Question", "QuestionOption", "QuestionType"]