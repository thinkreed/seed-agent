"""
AgentLoop 初始化和 Token 管理

职责:
- 模型和配置初始化
- Token 计算和编码
- 上下文窗口管理
"""

import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# 模块级 encoding 缓存
_ENCODING_CACHE: dict[str, tiktoken.Encoding] = {}


def get_tokenizer(gateway, model_id: str) -> tiktoken.Encoding | None:
    """获取 tokenizer (带缓存)"""
    model_name = model_id.split("/", 1)[-1] if "/" in model_id else model_id

    if model_name in _ENCODING_CACHE:
        return _ENCODING_CACHE[model_name]

    try:
        encoding = tiktoken.encoding_for_model(model_name)
        _ENCODING_CACHE[model_name] = encoding
        return encoding
    except KeyError:
        for enc_name in ["cl100k_base", "p50k_base", "r50k_base"]:
            if enc_name in _ENCODING_CACHE:
                return _ENCODING_CACHE[enc_name]
            try:
                encoding = tiktoken.get_encoding(enc_name)
                _ENCODING_CACHE[enc_name] = encoding
                return encoding
            except KeyError:
                continue
    return None


def get_context_window(gateway, model_id: str) -> int:
    """获取模型上下文窗口大小"""
    if "/" in model_id:
        provider_id, model_name = model_id.split("/", 1)
        provider = gateway.config.models.get(provider_id)
        if provider:
            for m in provider.models:
                if m.id == model_name:
                    return m.contextWindow
    return 100000


def setup_tools_and_skills() -> tuple[Any, Any]:
    """注册工具并加载技能"""
    from src.scheduler import register_scheduler_tools
    from src.tools import ToolRegistry
    from src.tools.builtin_tools import register_builtin_tools
    from src.tools.collaboration_tools import (
        register_tools as register_collaboration_tools,
    )
    from src.tools.memory_tools import register_memory_tools
    from src.tools.ralph_tools import register_ralph_tools
    from src.tools.skill_loader import register_skill_tools
    from src.tools.subagent_tools import register_subagent_tools

    tools = ToolRegistry()

    register_builtin_tools(tools)
    register_memory_tools(tools)
    register_skill_tools(tools)
    register_scheduler_tools(tools)
    register_ralph_tools(tools)
    register_subagent_tools(tools)
    register_collaboration_tools(tools)

    from src.tools.skill_loader import SkillLoader
    skill_loader = SkillLoader()

    return tools, skill_loader


def setup_subsystems(
    gateway,
    model_id: str,
    skill_loader,
    system_prompt: str | None = None,
) -> tuple[Any, Any, str]:
    """初始化子系统"""
    from src.subagent_manager import SubagentManager
    from src.tools.subagent_tools import init_subagent_manager

    subagent_manager = SubagentManager(
        gateway=gateway,
        model_id=model_id,
    )
    init_subagent_manager(subagent_manager)

    skills_prompt = skill_loader.get_skills_prompt()
    if system_prompt:
        final_prompt = system_prompt + "\n\n" + skills_prompt
    else:
        final_prompt = skills_prompt

    return subagent_manager, final_prompt


def setup_harness_trio(
    gateway,
    model_id: str,
    session,
    sandbox,
    max_iterations: int,
    system_prompt: str,
    context_window: int,
    enable_pruning: bool,
    hook_registry,
) -> tuple[Any, Any]:
    """初始化 Harness"""
    from src.harness import Harness
    from src.llm_client import LLMClient

    llm_client = LLMClient(gateway=gateway, model_id=model_id)

    harness = Harness(
        llm_client=llm_client,
        session=session,
        sandbox=sandbox,
        max_iterations=max_iterations,
        system_prompt=system_prompt,
        context_window=context_window,
        enable_pruning=enable_pruning,
        hook_registry=hook_registry,
    )

    logger.info(
        f"Harness trio initialized: model={model_id}, "
        f"context_window={context_window}"
    )

    return harness, llm_client


def setup_context_engineering(
    gateway,
    model_id: str,
    compression_config,
    pruning_config,
    harness,
) -> Any:
    """初始化上下文工程"""
    from src.context_engineering import ContextEngineering

    context_engineering = ContextEngineering(
        gateway=gateway,
        model_id=model_id,
        compression_config=compression_config,
        pruning_config=pruning_config,
    )

    harness._context_engineering = context_engineering

    logger.info(
        f"ContextEngineering initialized: "
        f"compression={compression_config is not None}"
    )

    return context_engineering