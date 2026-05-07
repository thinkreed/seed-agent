"""Hook 专用输出类型

Wiki 知识落地 (基于 Qwen-Code Hook 输出类设计):
- DefaultHookOutput: 默认 Hook 输出
- PreToolUseHookOutput: 工具调用前专用输出（支持拒绝/修改）
- PostToolUseHookOutput: 工具调用后专用输出（支持结果修改）
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DefaultHookOutput:
    """默认 Hook 输出 (Wiki 知识落地)

    所有 Hook 的基础输出类型。
    """

    success: bool = True
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreToolUseHookOutput(DefaultHookOutput):
    """工具调用前 Hook 输出 (Wiki 知识落地)

    支持拒绝工具调用、修改参数：
    - should_execute: 是否继续执行工具
    - modified_args: 修改后的参数（可选）
    - deny_reason: 拒绝原因（如果 should_execute=False）

    用途：
    - 安全检查 Hook 可拒绝危险工具调用
    - 参数校验 Hook 可修改参数
    """

    should_execute: bool = True
    modified_args: dict[str, Any] | None = None
    deny_reason: str | None = None


@dataclass
class PostToolUseHookOutput(DefaultHookOutput):
    """工具调用后 Hook 输出 (Wiki 知识落地)

    支持修改工具结果：
    - modified_result: 修改后的结果（可选）
    - should_continue: 是否继续执行后续 Hook

    用途：
    - 结果格式化 Hook 可修改输出
    - 日志记录 Hook 可记录结果
    """

    modified_result: Any | None = None
    should_continue: bool = True


@dataclass
class LLMStreamHookOutput(DefaultHookOutput):
    """LLM 流式响应 Hook 输出 (Wiki 知识落地)

    支持修改流式内容：
    - content_chunk: 内容片段（可修改）
    - should_emit: 是否发送到客户端

    用途：
    - 内容过滤 Hook 可修改敏感内容
    - 格式化 Hook 可调整输出格式
    """

    content_chunk: str = ""
    should_emit: bool = True


@dataclass
class UserResponseHookOutput(DefaultHookOutput):
    """用户响应 Hook 输出 (Wiki 知识落地)

    支持修改用户输入：
    - modified_response: 修改后的响应（可选）
    - should_process: 是否处理响应

    用途：
    - 输入验证 Hook 可校验用户输入
    - 预处理 Hook 可标准化输入
    """

    modified_response: str | None = None
    should_process: bool = True


__all__ = [
    "DefaultHookOutput",
    "LLMStreamHookOutput",
    "PostToolUseHookOutput",
    "PreToolUseHookOutput",
    "UserResponseHookOutput",
]