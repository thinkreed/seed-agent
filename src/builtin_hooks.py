"""
内置生命周期钩子定义

基于 Harness Engineering "确定性生命周期钩子" 设计：
- 在关键节点自动触发预设动作
- 由系统确保关键流程被执行
- 不依赖可能被模型遗忘的指令

钩子分类：
1. 会话生命周期钩子：session_start, session_end
2. 工具执行钩子：tool_call_before, tool_call_after
3. LLM 调用钩子：llm_call_before, llm_call_after
4. 响应钩子：response_before, response_after
5. 上下文钩子：context_reset_before, context_reset_after
6. 子代理钩子：subagent_spawn, subagent_end
7. Ralph Loop 钩子：ralph_iteration_start, ralph_iteration_end
"""

import logging
from collections.abc import Callable
from typing import Any

from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry

logger = logging.getLogger(__name__)


def register_builtin_hooks(registry: LifecycleHookRegistry) -> None:
    """注册所有内置钩子

    Args:
        registry: 钩子注册中心实例
    """
    # === 会话生命周期钩子 ===
    _register_session_hooks(registry)

    # === 工具执行钩子 ===
    _register_tool_hooks(registry)

    # === LLM 调用钩子 ===
    _register_llm_hooks(registry)

    # === 响应钩子 ===
    _register_response_hooks(registry)

    # === 上下文钩子 ===
    _register_context_hooks(registry)

    # === 子代理钩子 ===
    _register_subagent_hooks(registry)

    # === Ralph Loop 钩子 ===
    _register_ralph_hooks(registry)

    logger.info(f"Builtin hooks registered: total={registry.get_hook_count()}")


# === 会话生命周期钩子 ===

def _register_session_hooks(registry: LifecycleHookRegistry) -> None:
    """注册会话生命周期钩子"""

    @registry.register(HookPoint.SESSION_START, priority=0, name="session_log_start")
    def session_log_start(context: dict[str, Any]) -> None:
        """记录会话开始"""
        session_id = context.get("session_id", "unknown")
        metadata = context.get("metadata", {})
        logger.info(f"Session started: {session_id}, metadata={metadata}")

    @registry.register(HookPoint.SESSION_START, priority=1, name="session_init_state")
    def session_init_state(context: dict[str, Any]) -> None:
        """初始化会话状态"""
        session = context.get("session")
        if session:
            context["session_state"] = {
                "event_count": 0,
                "conversation_rounds": 0,
            }

    @registry.register(HookPoint.SESSION_END, priority=0, name="session_log_end")
    def session_log_end(context: dict[str, Any]) -> None:
        """记录会话结束"""
        session_id = context.get("session_id", "unknown")
        reason = context.get("reason", "normal")
        event_count = context.get("event_count", 0)
        logger.info(f"Session ended: {session_id}, reason={reason}, events={event_count}")

    @registry.register(HookPoint.SESSION_END, priority=1, name="session_persist_state")
    def session_persist_state(context: dict[str, Any]) -> None:
        """持久化会话状态"""
        session = context.get("session")
        if session and hasattr(session, "persist_state"):
            # 调用会话持久化方法（如果存在）
            pass  # 实际持久化由 SessionEventStream 完成

    @registry.register(HookPoint.SESSION_PAUSE, priority=0, name="session_log_pause")
    def session_log_pause(context: dict[str, Any]) -> None:
        """记录会话暂停"""
        session_id = context.get("session_id", "unknown")
        logger.info(f"Session paused: {session_id}")

    @registry.register(HookPoint.SESSION_RESUME, priority=0, name="session_log_resume")
    def session_log_resume(context: dict[str, Any]) -> None:
        """记录会话恢复"""
        session_id = context.get("session_id", "unknown")
        logger.info(f"Session resumed: {session_id}")


# === 工具执行钩子 ===

def _register_tool_hooks(registry: LifecycleHookRegistry) -> None:
    """注册工具执行钩子"""

    @registry.register(HookPoint.TOOL_CALL_BEFORE, priority=0, name="tool_permission_check")
    def tool_permission_check(context: dict[str, Any]) -> bool:
        """检查工具调用权限"""
        tool_name = context.get("tool_name")
        permission_set = context.get("permission_set")
        sandbox = context.get("sandbox")

        # 如果有 Sandbox，使用 Sandbox 权限检查
        if sandbox and hasattr(sandbox, "_check_permission"):
            tool_args = context.get("tool_args", {})
            if not sandbox._check_permission(tool_name, tool_args):
                raise PermissionError(
                    f"Tool '{tool_name}' not allowed in current sandbox"
                )

        # 如果有权限集，检查工具是否在权限集中
        if permission_set and tool_name:
            if isinstance(permission_set, dict):
                allowed = permission_set.get(tool_name, {}).get("action", "allow")
            elif isinstance(permission_set, (list, set)):
                allowed = tool_name in permission_set
            else:
                allowed = True

            if not allowed:
                raise PermissionError(
                    f"Tool '{tool_name}' not in permission set"
                )

        return True

    @registry.register(HookPoint.TOOL_CALL_BEFORE, priority=1, name="tool_log_call")
    def tool_log_call(context: dict[str, Any]) -> None:
        """记录工具调用"""
        tool_name = context.get("tool_name", "unknown")
        tool_args = context.get("tool_args", {})
        tool_call_id = context.get("tool_call_id", "unknown")
        logger.debug(f"Tool call: {tool_name} (id={tool_call_id}), args={tool_args}")

    @registry.register(HookPoint.TOOL_CALL_BEFORE, priority=2, name="tool_path_mapping")
    def tool_path_mapping(context: dict[str, Any]) -> None:
        """路径映射（如果有 Sandbox）"""
        sandbox = context.get("sandbox")
        tool_args = context.get("tool_args", {})

        if sandbox and hasattr(sandbox, "_map_paths"):
            mapped_args = sandbox._map_paths(tool_args)
            context["mapped_args"] = mapped_args

    @registry.register(HookPoint.TOOL_CALL_AFTER, priority=0, name="tool_validate_result")
    def tool_validate_result(context: dict[str, Any]) -> None:
        """验证工具结果"""
        result = context.get("result")
        tool_name = context.get("tool_name", "unknown")

        if result is None:
            logger.warning(f"Tool {tool_name} returned None")

        # 检查错误标识
        if isinstance(result, str):
            if result.startswith("Error:") or "error" in result.lower():
                logger.warning(f"Tool {tool_name} returned error: {result[:100]}")

    @registry.register(HookPoint.TOOL_CALL_AFTER, priority=1, name="tool_log_result")
    def tool_log_result(context: dict[str, Any]) -> None:
        """记录工具结果"""
        tool_name = context.get("tool_name", "unknown")
        result = context.get("result")
        duration_ms = context.get("duration_ms", 0)

        # 截断结果日志
        result_str = str(result)[:200] if result else "None"
        logger.debug(f"Tool result: {tool_name}, duration={duration_ms:.2f}ms, result={result_str}")

    @registry.register(HookPoint.TOOL_CALL_ERROR, priority=0, name="tool_log_error")
    def tool_log_error(context: dict[str, Any]) -> None:
        """记录工具错误"""
        tool_name = context.get("tool_name", "unknown")
        error = context.get("error", "unknown error")
        tool_args = context.get("tool_args", {})

        logger.error(f"Tool error: {tool_name}, args={tool_args}, error={error}")

    @registry.register(HookPoint.TOOL_CALL_ERROR, priority=1, name="tool_record_failure")
    def tool_record_failure(context: dict[str, Any]) -> None:
        """记录工具失败统计"""
        session = context.get("session")
        tool_name = context.get("tool_name", "unknown")
        error = context.get("error", "")

        if session and hasattr(session, "emit_event"):
            session.emit_event("error_occurred", {
                "error_type": "tool_execution",
                "tool_name": tool_name,
                "error_message": error[:500],
            })


# === LLM 调用钩子 ===

def _register_llm_hooks(registry: LifecycleHookRegistry) -> None:
    """注册 LLM 调用钩子"""

    @registry.register(HookPoint.LLM_CALL_BEFORE, priority=0, name="llm_log_call")
    def llm_log_call(context: dict[str, Any]) -> None:
        """记录 LLM 调用"""
        model_id = context.get("model_id", "unknown")
        messages_count = len(context.get("messages", []))
        tools_count = len(context.get("tools", []))

        logger.debug(
            f"LLM call: model={model_id}, "
            f"messages={messages_count}, tools={tools_count}"
        )

    @registry.register(HookPoint.LLM_CALL_BEFORE, priority=1, name="llm_context_check")
    def llm_context_check(context: dict[str, Any]) -> None:
        """检查上下文大小"""
        messages = context.get("messages", [])
        context_window = context.get("context_window", 100000)

        # 简单估算 token 数
        total_chars = sum(
            len(m.get("content", "")) if isinstance(m.get("content"), str) else 0
            for m in messages
        )
        estimated_tokens = int(total_chars * 0.5)

        if estimated_tokens > context_window * 0.75:
            logger.warning(
                f"Context near limit: estimated={estimated_tokens}, "
                f"window={context_window}"
            )
            context["context_near_limit"] = True

    @registry.register(HookPoint.LLM_CALL_AFTER, priority=0, name="llm_validate_response")
    def llm_validate_response(context: dict[str, Any]) -> None:
        """验证 LLM 响应"""
        response = context.get("response")

        if response is None:
            raise ValueError("LLM response is None")

        choices = response.get("choices", [])
        if not choices:
            raise ValueError("LLM response has no choices")

        # 检查是否有效内容
        message = choices[0].get("message", {})
        has_content = message.get("content") is not None
        has_tool_calls = message.get("tool_calls") is not None

        if not has_content and not has_tool_calls:
            logger.warning("LLM response has neither content nor tool_calls")

    @registry.register(HookPoint.LLM_CALL_AFTER, priority=1, name="llm_log_response")
    def llm_log_response(context: dict[str, Any]) -> None:
        """记录 LLM 响应"""
        response = context.get("response")
        duration_ms = context.get("duration_ms", 0)

        choices = response.get("choices", []) if response else []
        message = choices[0].get("message", {}) if choices else {}

        content_preview = str(message.get("content", ""))[:50]
        tool_calls_count = len(message.get("tool_calls", []))

        logger.debug(
            f"LLM response: duration={duration_ms:.2f}ms, "
            f"content={content_preview}..., tool_calls={tool_calls_count}"
        )

    @registry.register(HookPoint.LLM_STREAM_START, priority=0, name="llm_log_stream_start")
    def llm_log_stream_start(context: dict[str, Any]) -> None:
        """记录流式响应开始"""
        model_id = context.get("model_id", "unknown")
        logger.debug(f"LLM stream started: model={model_id}")

    @registry.register(HookPoint.LLM_STREAM_CHUNK, priority=0, name="llm_accumulate_chunk")
    def llm_accumulate_chunk(context: dict[str, Any]) -> None:
        """累积流式响应块"""
        chunk = context.get("chunk")
        accumulator = context.get("accumulator")

        if accumulator is not None and chunk:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                accumulator["content"] = accumulator.get("content", "") + content

    @registry.register(HookPoint.LLM_STREAM_END, priority=0, name="llm_log_stream_end")
    def llm_log_stream_end(context: dict[str, Any]) -> None:
        """记录流式响应结束"""
        duration_ms = context.get("duration_ms", 0)
        total_chunks = context.get("total_chunks", 0)

        logger.debug(
            f"LLM stream ended: duration={duration_ms:.2f}ms, "
            f"chunks={total_chunks}"
        )


# === 响应钩子 ===

def _register_response_hooks(registry: LifecycleHookRegistry) -> None:
    """注册响应钩子"""

    @registry.register(HookPoint.RESPONSE_BEFORE, priority=0, name="response_log_prepare")
    def response_log_prepare(context: dict[str, Any]) -> None:
        """记录响应准备"""
        iteration = context.get("iteration", 0)
        max_iterations = context.get("max_iterations", 30)

        logger.debug(f"Preparing response: iteration={iteration}/{max_iterations}")

    @registry.register(HookPoint.RESPONSE_AFTER, priority=0, name="response_update_state")
    def response_update_state(context: dict[str, Any]) -> None:
        """更新响应状态"""
        session = context.get("session")
        response = context.get("response")

        if session and response:
            context["last_response"] = response

    @registry.register(HookPoint.RESPONSE_AFTER, priority=1, name="response_check_completion")
    def response_check_completion(context: dict[str, Any]) -> None:
        """检查是否完成"""
        response = context.get("response")
        choices = response.get("choices", []) if response else []
        message = choices[0].get("message", {}) if choices else {}

        has_tool_calls = message.get("tool_calls") is not None
        context["should_continue"] = has_tool_calls

    @registry.register(HookPoint.RESPONSE_AFTER, priority=2, name="response_metrics_update")
    def response_metrics_update(context: dict[str, Any]) -> None:
        """更新响应指标"""
        harness = context.get("harness")
        metrics = context.get("metrics")

        if harness and metrics:
            if hasattr(harness, "_metrics"):
                harness._metrics.append(metrics)


# === 上下文钩子 ===

def _register_context_hooks(registry: LifecycleHookRegistry) -> None:
    """注册上下文钩子"""

    @registry.register(HookPoint.CONTEXT_RESET_BEFORE, priority=0, name="context_log_reset")
    def context_log_reset(context: dict[str, Any]) -> None:
        """记录上下文重置"""
        reason = context.get("reason", "unknown")
        event_count = context.get("event_count", 0)

        logger.info(f"Context reset: reason={reason}, events={event_count}")

    @registry.register(HookPoint.CONTEXT_RESET_BEFORE, priority=1, name="context_extract_critical")
    def context_extract_critical(context: dict[str, Any]) -> None:
        """提取关键上下文"""
        history = context.get("history", [])

        # 提取最后几条关键消息
        critical_messages = history[-5:] if len(history) > 5 else history
        context["critical_context"] = critical_messages

    @registry.register(HookPoint.CONTEXT_RESET_AFTER, priority=0, name="context_inject_preserved")
    def context_inject_preserved(context: dict[str, Any]) -> None:
        """注入保留上下文"""
        preserved = context.get("preserved_context")
        history = context.get("history")

        if preserved and history is not None:
            # 添加状态摘要作为系统消息
            history.append({
                "role": "system",
                "content": f"[状态摘要]\n{preserved}"
            })

    @registry.register(HookPoint.SUMMARY_GENERATED, priority=0, name="summary_log")
    def summary_log(context: dict[str, Any]) -> None:
        """记录摘要生成"""
        summary = context.get("summary", "")
        covers_events = context.get("covers_events", [])

        logger.info(
            f"Summary generated: covers {len(covers_events)} events, "
            f"length={len(summary)}"
        )

    @registry.register(HookPoint.SUMMARY_GENERATED, priority=1, name="summary_record")
    def summary_record(context: dict[str, Any]) -> None:
        """记录摘要到会话"""
        session = context.get("session")
        summary = context.get("summary", "")

        if session and hasattr(session, "create_summary_marker"):
            event_count = session.get_event_count()
            session.create_summary_marker(event_count, summary)


# === 子代理钩子 ===

def _register_subagent_hooks(registry: LifecycleHookRegistry) -> None:
    """注册子代理钩子"""

    @registry.register(HookPoint.SUBAGENT_SPAWN, priority=0, name="subagent_log_spawn")
    def subagent_log_spawn(context: dict[str, Any]) -> None:
        """记录子代理创建"""
        subagent_id = context.get("subagent_id", "unknown")
        subagent_type = context.get("subagent_type", "unknown")
        prompt_preview = str(context.get("prompt", ""))[:50]

        logger.info(
            f"Subagent spawned: id={subagent_id}, type={subagent_type}, "
            f"prompt={prompt_preview}..."
        )

    @registry.register(HookPoint.SUBAGENT_START, priority=0, name="subagent_log_start")
    def subagent_log_start(context: dict[str, Any]) -> None:
        """记录子代理开始"""
        subagent_id = context.get("subagent_id", "unknown")

        logger.debug(f"Subagent started: id={subagent_id}")

    @registry.register(HookPoint.SUBAGENT_END, priority=0, name="subagent_log_end")
    def subagent_log_end(context: dict[str, Any]) -> None:
        """记录子代理结束"""
        subagent_id = context.get("subagent_id", "unknown")
        result_preview = str(context.get("result", ""))[:100]
        duration_ms = context.get("duration_ms", 0)

        logger.info(
            f"Subagent ended: id={subagent_id}, "
            f"duration={duration_ms:.2f}ms, result={result_preview}..."
        )

    @registry.register(HookPoint.SUBAGENT_ERROR, priority=0, name="subagent_log_error")
    def subagent_log_error(context: dict[str, Any]) -> None:
        """记录子代理错误"""
        subagent_id = context.get("subagent_id", "unknown")
        error = context.get("error", "unknown error")

        logger.error(f"Subagent error: id={subagent_id}, error={error}")


# === Ralph Loop 钩子 ===

def _register_ralph_hooks(registry: LifecycleHookRegistry) -> None:
    """注册 Ralph Loop 钩子"""

    @registry.register(HookPoint.RALPH_ITERATION_START, priority=0, name="ralph_log_iteration")
    def ralph_log_iteration(context: dict[str, Any]) -> None:
        """记录 Ralph 迭代开始"""
        iteration = context.get("iteration", 0)
        max_iterations = context.get("max_iterations", 1000)

        logger.debug(f"Ralph iteration: {iteration}/{max_iterations}")

    @registry.register(HookPoint.RALPH_ITERATION_END, priority=0, name="ralph_persist_state")
    def ralph_persist_state(context: dict[str, Any]) -> None:
        """持久化 Ralph 状态"""
        ralph = context.get("ralph_loop")
        response = context.get("response")

        if ralph and hasattr(ralph, "_persist_state"):
            ralph._persist_state(response)

    @registry.register(HookPoint.RALPH_COMPLETION_CHECK, priority=0, name="ralph_log_check")
    def ralph_log_check(context: dict[str, Any]) -> None:
        """记录 Ralph 完成检查"""
        completion_type = context.get("completion_type", "unknown")
        criteria = context.get("completion_criteria", {})

        logger.debug(f"Ralph completion check: type={completion_type}, criteria={criteria}")

    @registry.register(HookPoint.RALPH_CONTEXT_RESET, priority=0, name="ralph_log_reset")
    def ralph_log_reset(context: dict[str, Any]) -> None:
        """记录 Ralph 上下文重置"""
        iteration = context.get("iteration", 0)
        reason = context.get("reason", "periodic")

        logger.info(f"Ralph context reset: iteration={iteration}, reason={reason}")


# === 自定义钩子注册辅助 ===

def register_custom_hook(
    registry: LifecycleHookRegistry,
    hook_point: HookPoint,
    callback: Callable[..., Any],
    priority: int = 100,
    name: str | None = None,
) -> str:
    """注册自定义钩子

    Args:
        registry: 钩子注册中心
        hook_point: 钩子节点
        callback: 钩子回调
        priority: 优先级（默认 100，在内置钩子之后执行）
        name: 钩子名称

    Returns:
        hook_id: 钩子唯一标识
    """
    result = registry.register(hook_point, callback, priority=priority, name=name)
    # 当直接传入 callback 时，返回的是 str (hook_id)
    return result if isinstance(result, str) else callback.__name__


def create_hook_context(**kwargs) -> dict[str, Any]:
    """创建钩子上下文

    Args:
        **kwargs: 上下文参数

    Returns:
        钩子上下文字典
    """
    return kwargs