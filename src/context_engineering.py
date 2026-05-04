"""
上下文工程模块

基于 Harness Engineering "上下文工程" 设计：
- 渐进式压缩：最新完整保留 → 稍旧轻量总结 → 更早简短摘要
- 智能裁剪：根据任务相关性过滤不相关历史
- 原始数据不丢失：Session 保留完整历史

核心组件：
- ProgressiveContextCompressor: 三层渐进压缩
- IntelligentContextPruner: 智能裁剪
- ContextEngineering: 集成管理器

特性：
- 渐进信息损失，不丢失原始数据
- 相关性过滤，保留关键信息
- 上下文利用率提升，避免浪费 Token
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway
from src.session_event_stream import EventType, SessionEventStream

logger = logging.getLogger(__name__)

# 预编译正则表达式（性能优化）
_RE_FILE_PATTERN = re.compile(r"[a-zA-Z_./]+\.[a-zA-Z]+")
_RE_CODE_PATTERN = re.compile(r"[A-Z][a-zA-Z0-9]*|[a-z_][a-z0-9_]*")
_RE_STOP_WORDS = {"the", "for", "and", "with", "this", "that"}

# 相关性阈值
RELEVANCE_THRESHOLD = 0.3


class CompressionTier(str, Enum):
    """压缩层级枚举"""

    TIER_1_FULL = "tier_1_full"  # 最新完整保留
    TIER_2_LIGHT = "tier_2_light"  # 稍旧轻量总结
    TIER_3_ABSTRACT = "tier_3_abstract"  # 更早简短摘要


@dataclass
class TierConfig:
    """层级配置"""

    name: str
    threshold: float  # 容量阈值触发点
    keep_rounds: int  # 保留轮数 (一轮 ≈ 2 条消息)
    method: CompressionTier
    description: str


@dataclass
class CompressionConfig:
    """压缩配置"""

    tiers: dict[CompressionTier, TierConfig] = field(
        default_factory=lambda: {
            CompressionTier.TIER_1_FULL: TierConfig(
                name="recent_full",
                threshold=0.0,
                keep_rounds=5,
                method=CompressionTier.TIER_1_FULL,
                description="最新 5 轮对话完整保留",
            ),
            CompressionTier.TIER_2_LIGHT: TierConfig(
                name="medium_light",
                threshold=0.5,
                keep_rounds=10,
                method=CompressionTier.TIER_2_LIGHT,
                description="稍旧 10 轮轻量总结",
            ),
            CompressionTier.TIER_3_ABSTRACT: TierConfig(
                name="old_abstract",
                threshold=0.75,
                keep_rounds=0,  # 全部压缩
                method=CompressionTier.TIER_3_ABSTRACT,
                description="更早历史简短摘要",
            ),
        }
    )

    # Token 估算系数
    token_per_char: float = 0.5

    # 最大上下文限制
    max_context_messages: int = 50


@dataclass
class PruningConfig:
    """裁剪配置"""

    relevance_threshold: float = RELEVANCE_THRESHOLD

    # 实体类型权重
    entity_weights: dict[str, float] = field(
        default_factory=lambda: {
            "file_path": 1.0,
            "function_name": 0.8,
            "class_name": 0.8,
            "keyword": 0.5,
        }
    )

    # 角色权重
    role_weights: dict[str, float] = field(
        default_factory=lambda: {
            "user": 1.0,
            "assistant": 1.0,
            "tool": 0.7,
            "system": 0.5,
        }
    )

    # 最小保留消息数
    min_preserve_count: int = 5


class ProgressiveContextCompressor:
    """渐进式上下文压缩

    三层压缩策略：
    - Tier 1: 最新 5 轮完整保留 (Full)
    - Tier 2: 稍旧 10 轮轻量总结 (Light Summary) - 50% 容量时触发
    - Tier 3: 更早历史简短摘要 (Abstract) - 75% 容量时触发

    核心特性：
    - 渐进信息损失，不丢失原始数据（Session 保留）
    - 根据上下文使用率动态选择压缩层级
    """

    LIGHT_SUMMARY_PROMPT = """请对以下对话片段进行轻量总结，保留主要操作和结果：

{messages}

轻量总结格式：
- 主要操作: ...
- 关键结果: ...
- 重要发现: ...

请用简洁的要点形式输出（不超过200字）："""

    ABSTRACT_SUMMARY_PROMPT = """请用1-2句话总结以下对话片段的核心结论：

{messages}

格式: 核心结论是..."""

    def __init__(
        self,
        gateway: "LLMGateway",
        model_id: str,
        config: CompressionConfig | None = None,
    ):
        """初始化压缩器

        Args:
            gateway: LLM Gateway 实例（用于生成摘要）
            model_id: 模型 ID
            config: 压缩配置
        """
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or CompressionConfig()

    def compress(
        self,
        session: SessionEventStream,
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """应用三层压缩

        Args:
            session: 事件流（原始数据不丢失）
            context_window: 上下文窗口大小
            system_prompt: 系统提示

        Returns:
            压缩后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._build_history_from_session(session, system_prompt)

        # 2. 计算当前容量使用率
        current_tokens = self._estimate_tokens(full_history)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        logger.debug(
            f"Compressing context: tokens={current_tokens}/{context_window}, "
            f"usage={usage_ratio:.2%}"
        )

        # 3. 根据使用率决定压缩层级
        if usage_ratio < self._config.tiers[CompressionTier.TIER_2_LIGHT].threshold:
            # 低使用率：Tier 1 仅
            compressed = self._apply_tier_1_only(full_history)
        elif (
            usage_ratio < self._config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold
        ):
            # 中使用率：Tier 1 + Tier 2
            compressed = self._apply_tier_1_and_2(full_history)
        else:
            # 高使用率：完整三层
            compressed = self._apply_all_tiers(full_history)

        # 4. 应用消息数量限制
        if len(compressed) > self._config.max_context_messages:
            compressed = compressed[-self._config.max_context_messages :]

        logger.info(
            f"Context compressed: {len(full_history)} -> {len(compressed)} messages, "
            f"usage={usage_ratio:.2%}"
        )

        return compressed

    async def compress_async(
        self,
        session: SessionEventStream,
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """异步应用三层压缩（使用 LLM 生成摘要）

        Args:
            session: 事件流
            context_window: 上下文窗口大小
            system_prompt: 系统提示

        Returns:
            压缩后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._build_history_from_session(session, system_prompt)

        # 2. 计算当前容量使用率
        current_tokens = self._estimate_tokens(full_history)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        logger.debug(
            f"Async compressing context: tokens={current_tokens}/{context_window}, "
            f"usage={usage_ratio:.2%}"
        )

        # 3. 根据使用率决定压缩层级
        if usage_ratio < self._config.tiers[CompressionTier.TIER_2_LIGHT].threshold:
            compressed = self._apply_tier_1_only(full_history)
        elif (
            usage_ratio < self._config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold
        ):
            compressed = await self._apply_tier_1_and_2_async(full_history)
        else:
            compressed = await self._apply_all_tiers_async(full_history)

        # 4. 应用消息数量限制
        if len(compressed) > self._config.max_context_messages:
            compressed = compressed[-self._config.max_context_messages :]

        logger.info(
            f"Context async compressed: {len(full_history)} -> {len(compressed)} messages"
        )

        return compressed

    def _build_history_from_session(
        self, session: SessionEventStream, system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        """从 Session 构建完整历史（包括摘要）"""
        messages: list[dict[str, Any]] = []

        # 系统提示
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 获取最近的摘要标记
        last_summary = session.find_last_summary_marker()

        # 添加摘要作为上下文
        if last_summary:
            summary_content = last_summary["data"].get("summary", "")
            if summary_content:
                messages.append(
                    {"role": "user", "content": f"[历史摘要]\n{summary_content}"}
                )

        # 获取摘要后的事件
        recent_events = session.get_events_since_last_summary(
            [EventType.USER_INPUT, EventType.LLM_RESPONSE, EventType.TOOL_RESULT]
        )

        # 转换事件为消息
        for event in recent_events:
            msg = self._event_to_message(event)
            if msg:
                messages.append(msg)

        return messages

    def _event_to_message(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """将事件转换为消息格式"""
        event_type = event["type"]
        data = event["data"]

        if event_type == EventType.USER_INPUT.value:
            return {"role": "user", "content": data.get("content", "")}

        if event_type == EventType.LLM_RESPONSE.value:
            msg: dict[str, Any] = {"role": "assistant"}
            content = data.get("content")
            if content:
                msg["content"] = content
            if data.get("tool_calls"):
                msg["tool_calls"] = data["tool_calls"]
            return msg

        if event_type == EventType.TOOL_RESULT.value:
            return {
                "role": "tool",
                "tool_call_id": data.get("tool_call_id"),
                "content": data.get("content", ""),
            }

        return None

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算 Token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                # 使用字符数 * 系数估算
                total += int(len(content) * self._config.token_per_char)

            # Tool calls 也计入
            if msg.get("tool_calls"):
                tc_str = str(msg["tool_calls"])
                total += int(len(tc_str) * self._config.token_per_char)

        return total

    def _apply_tier_1_only(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """仅 Tier 1: 最新轮完整保留"""
        tier_1_config = self._config.tiers[CompressionTier.TIER_1_FULL]
        keep_messages = tier_1_config.keep_rounds * 2  # 一轮 ≈ 2 条消息

        # 保留系统提示和摘要
        system_and_summary = [
            m
            for m in history
            if m["role"] in ["system", "user"] and "摘要" in m.get("content", "")
        ]

        # 最新消息
        recent = history[-keep_messages:] if len(history) > keep_messages else history

        # 合并，去重
        compressed = system_and_summary[:]
        for m in recent:
            if m not in compressed:
                compressed.append(m)

        return compressed

    def _apply_tier_1_and_2(
        self, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Tier 1 + Tier 2: 同步版本（不使用 LLM）"""
        tier_1_config = self._config.tiers[CompressionTier.TIER_1_FULL]
        tier_2_config = self._config.tiers[CompressionTier.TIER_2_LIGHT]

        tier_1_messages = tier_1_config.keep_rounds * 2
        tier_2_messages = tier_2_config.keep_rounds * 2

        # Tier 1: 最新完整保留
        tier_1 = (
            history[-tier_1_messages:] if len(history) > tier_1_messages else history
        )

        # Tier 2: 稍旧部分
        tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
        tier_2_end = len(history) - tier_1_messages
        tier_2 = history[tier_2_start:tier_2_end]

        compressed = []

        # Tier 2: 简化格式（不使用 LLM）
        if tier_2:
            simplified = self._simplify_messages(tier_2)
            if simplified:
                compressed.append(
                    {
                        "role": "system",
                        "content": f"[中等对话摘要]\n{self._format_simplified(simplified)}",
                    }
                )

        # Tier 1
        compressed.extend(tier_1)

        return compressed

    async def _apply_tier_1_and_2_async(
        self, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Tier 1 + Tier 2: 异步版本（使用 LLM 生成摘要）"""
        tier_1_config = self._config.tiers[CompressionTier.TIER_1_FULL]
        tier_2_config = self._config.tiers[CompressionTier.TIER_2_LIGHT]

        tier_1_messages = tier_1_config.keep_rounds * 2
        tier_2_messages = tier_2_config.keep_rounds * 2

        # Tier 1: 最新完整保留
        tier_1 = (
            history[-tier_1_messages:] if len(history) > tier_1_messages else history
        )

        # Tier 2: 稍旧部分
        tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
        tier_2_end = len(history) - tier_1_messages
        tier_2 = history[tier_2_start:tier_2_end]

        compressed = []

        # Tier 2: 使用 LLM 轻量总结
        if tier_2:
            light_summary = await self._light_summarize(tier_2)
            if light_summary:
                compressed.append(
                    {"role": "system", "content": f"[中等对话摘要]\n{light_summary}"}
                )

        # Tier 1
        compressed.extend(tier_1)

        return compressed

    def _apply_all_tiers(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """完整三层: 同步版本"""
        tier_1_config = self._config.tiers[CompressionTier.TIER_1_FULL]
        tier_2_config = self._config.tiers[CompressionTier.TIER_2_LIGHT]

        tier_1_messages = tier_1_config.keep_rounds * 2
        tier_2_messages = tier_2_config.keep_rounds * 2

        # Tier 1: 最新
        tier_1 = (
            history[-tier_1_messages:] if len(history) > tier_1_messages else history
        )

        # Tier 2: 稍旧
        tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
        tier_2_end = len(history) - tier_1_messages
        tier_2 = history[tier_2_start:tier_2_end]

        # Tier 3: 更早
        tier_3 = history[:tier_2_start]

        compressed = []

        # Tier 3: 简短摘要（简化）
        if tier_3:
            abstract = self._simplify_messages(tier_3)
            if abstract:
                compressed.append(
                    {
                        "role": "system",
                        "content": f"[历史摘要 - 简短]\n{self._format_abstract(abstract)}",
                    }
                )

        # Tier 2: 轻量总结（简化）
        if tier_2:
            simplified = self._simplify_messages(tier_2)
            if simplified:
                compressed.append(
                    {
                        "role": "system",
                        "content": f"[中等对话摘要]\n{self._format_simplified(simplified)}",
                    }
                )

        # Tier 1
        compressed.extend(tier_1)

        return compressed

    async def _apply_all_tiers_async(
        self, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """完整三层: 异步版本（使用 LLM）"""
        tier_1_config = self._config.tiers[CompressionTier.TIER_1_FULL]
        tier_2_config = self._config.tiers[CompressionTier.TIER_2_LIGHT]

        tier_1_messages = tier_1_config.keep_rounds * 2
        tier_2_messages = tier_2_config.keep_rounds * 2

        # Tier 1: 最新
        tier_1 = (
            history[-tier_1_messages:] if len(history) > tier_1_messages else history
        )

        # Tier 2: 稍旧
        tier_2_start = max(0, len(history) - tier_1_messages - tier_2_messages)
        tier_2_end = len(history) - tier_1_messages
        tier_2 = history[tier_2_start:tier_2_end]

        # Tier 3: 更早
        tier_3 = history[:tier_2_start]

        compressed = []

        # Tier 3: 使用 LLM 简短摘要
        if tier_3:
            abstract = await self._abstract_summarize(tier_3)
            if abstract:
                compressed.append(
                    {"role": "system", "content": f"[历史摘要 - 简短]\n{abstract}"}
                )

        # Tier 2: 使用 LLM 轻量总结
        if tier_2:
            light_summary = await self._light_summarize(tier_2)
            if light_summary:
                compressed.append(
                    {"role": "system", "content": f"[中等对话摘要]\n{light_summary}"}
                )

        # Tier 1
        compressed.extend(tier_1)

        return compressed

    def _simplify_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """简化消息（提取关键信息）"""
        simplified = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if not content:
                continue

            # 提取关键信息
            key_info = self._extract_key_info(content)
            if key_info:
                simplified.append({"role": role, "key_info": key_info})

        return simplified

    def _extract_key_info(self, content: str) -> str:
        """提取内容的关键信息"""
        # 限制长度
        max_len = 100
        if len(content) <= max_len:
            return content

        # 提取关键句子（包含特定关键词）
        keywords = ["完成", "成功", "错误", "Error", "result", "输出", "创建", "修改"]
        sentences = content.split("\n")

        key_sentences = []
        for sentence in sentences:
            if any(kw in sentence for kw in keywords):
                key_sentences.append(sentence[:max_len])

        if key_sentences:
            return "\n".join(key_sentences[:3])

        # 无关键词时返回首尾
        return content[:50] + "..." + content[-50:]

    def _format_simplified(self, simplified: list[dict[str, Any]]) -> str:
        """格式化简化摘要"""
        lines = []
        for item in simplified[:10]:  # 最多 10 条
            role = item.get("role", "")
            key_info = item.get("key_info", "")
            lines.append(f"- [{role}]: {key_info[:80]}")

        return "\n".join(lines)

    def _format_abstract(self, simplified: list[dict[str, Any]]) -> str:
        """格式化简短摘要"""
        # 统计信息
        user_count = sum(1 for i in simplified if i.get("role") == "user")
        assistant_count = sum(1 for i in simplified if i.get("role") == "assistant")
        tool_count = sum(1 for i in simplified if i.get("role") == "tool")

        return (
            f"早期对话: {user_count} 条用户输入, "
            f"{assistant_count} 条响应, {tool_count} 条工具调用"
        )

    async def _light_summarize(self, messages: list[dict[str, Any]]) -> str | None:
        """轻量总结: 保留主要操作和结果（使用 LLM）"""
        formatted = self._format_messages_for_summary(messages)

        if not formatted:
            return None

        prompt = self.LIGHT_SUMMARY_PROMPT.format(messages=formatted)

        try:
            response = await self._gateway.chat_completion(
                self._model_id, [{"role": "user", "content": prompt}], tools=None
            )
            choices = response.get("choices", [])
            if not choices:
                logger.warning("Light summary: LLM returned empty choices")
                simplified = self._simplify_messages(messages)
                return self._format_simplified(simplified)
            summary = choices[0].get("message", {}).get("content", "")
            if not summary:
                simplified = self._simplify_messages(messages)
                return self._format_simplified(simplified)
            return summary.strip()
        except Exception as e:
            logger.warning(f"Light summary generation failed: {type(e).__name__}: {e}")
            # Fallback: 使用简化版本
            simplified = self._simplify_messages(messages)
            return self._format_simplified(simplified)

    async def _abstract_summarize(self, messages: list[dict[str, Any]]) -> str | None:
        """简短摘要: 仅保留核心结论（使用 LLM）"""
        formatted = self._format_messages_for_summary(messages)

        if not formatted:
            return None

        prompt = self.ABSTRACT_SUMMARY_PROMPT.format(messages=formatted)

        try:
            response = await self._gateway.chat_completion(
                self._model_id, [{"role": "user", "content": prompt}], tools=None
            )
            choices = response.get("choices", [])
            if not choices:
                logger.warning("Abstract summary: LLM returned empty choices")
                simplified = self._simplify_messages(messages)
                return self._format_abstract(simplified)
            summary = choices[0].get("message", {}).get("content", "")
            if not summary:
                simplified = self._simplify_messages(messages)
                return self._format_abstract(simplified)
            return summary.strip()
        except Exception as e:
            logger.warning(
                f"Abstract summary generation failed: {type(e).__name__}: {e}"
            )
            # Fallback: 使用统计版本
            simplified = self._simplify_messages(messages)
            return self._format_abstract(simplified)

    def _format_messages_for_summary(self, messages: list[dict[str, Any]]) -> str:
        """格式化消息用于摘要"""
        lines = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if not content:
                if msg.get("tool_calls"):
                    tc_names = [
                        tc.get("function", {}).get("name", "")
                        for tc in msg["tool_calls"]
                    ]
                    content = f"[Tool Calls: {', '.join(tc_names)}]"
                else:
                    continue

            # 限制长度
            if len(content) > 200:
                content = content[:200] + "..."

            lines.append(f"{role}: {content}")

        return "\n".join(lines)


class IntelligentContextPruner:
    """智能上下文裁剪

    根据当前任务相关性裁剪不相关历史：
    - 实体提取：文件路径、函数名、类名、关键词
    - 相关性计算：entity_matches + 角色权重
    - 语义相关性：使用 LLM 评估（可选）

    核心特性：
    - 保留高相关性消息
    - 添加裁剪说明
    - 最小保留数量保护
    """

    def __init__(
        self,
        gateway: "LLMGateway | None" = None,
        model_id: str | None = None,
        config: PruningConfig | None = None,
    ):
        """初始化裁剪器

        Args:
            gateway: LLM Gateway 实例（可选，用于语义相关性）
            model_id: 模型 ID
            config: 裁剪配置
        """
        self._gateway = gateway
        self._model_id = model_id
        self._config = config or PruningConfig()

    def prune_for_task(
        self, history: list[dict[str, Any]], current_task: str
    ) -> list[dict[str, Any]]:
        """根据当前任务裁剪不相关上下文

        Args:
            history: 完整历史
            current_task: 当前任务描述

        Returns:
            裁剪后的历史（保留高相关性）
        """
        # 1. 系统消息和摘要消息总是保留
        always_preserve = [
            m
            for m in history
            if m["role"] == "system" or "摘要" in m.get("content", "")
        ]

        # 2. 可裁剪的消息
        prunable = [
            m
            for m in history
            if m["role"] not in ["system"] and "摘要" not in m.get("content", "")
        ]

        if not prunable:
            return history

        # 3. 提取任务关键实体
        entities = self._extract_entities(current_task)

        if not entities:
            # 无实体时保留所有
            return history

        # 4. 计算相关性分数
        relevance_scores = self._compute_relevance(prunable, entities)

        # 5. 保留高相关性消息
        pruned = []
        for msg, score in zip(prunable, relevance_scores, strict=True):
            if score > self._config.relevance_threshold:
                pruned.append(msg)

        # 6. 最小保留保护
        if len(pruned) < self._config.min_preserve_count:
            # 按分数排序，保留最高的 min_preserve_count 条
            scored_msgs = sorted(
                zip(prunable, relevance_scores, strict=True),
                key=lambda x: x[1],
                reverse=True,
            )
            pruned = [m for m, s in scored_msgs[: self._config.min_preserve_count]]

        # 7. 合并结果
        result = always_preserve + pruned

        # 8. 添加裁剪说明
        if len(result) < len(history):
            filtered_count = len(history) - len(result)
            result.append(
                {
                    "role": "system",
                    "content": f"[裁剪说明: 已过滤 {filtered_count} 条低相关性历史，保留 {len(result)} 条]",
                }
            )

        logger.info(
            f"Context pruned for task: {len(history)} -> {len(result)} messages, "
            f"entities={len(entities)}"
        )

        return result

    async def prune_with_semantic_relevance(
        self, history: list[dict[str, Any]], current_task: str
    ) -> list[dict[str, Any]]:
        """使用语义相关性裁剪（LLM 评估）

        Args:
            history: 完整历史
            current_task: 当前任务描述

        Returns:
            裁剪后的历史
        """
        if not self._gateway or not self._model_id:
            # 无 LLM 时使用实体匹配
            return self.prune_for_task(history, current_task)

        # 系统消息和摘要消息总是保留
        always_preserve = [
            m
            for m in history
            if m["role"] == "system" or "摘要" in m.get("content", "")
        ]

        prunable = [
            m
            for m in history
            if m["role"] not in ["system"] and "摘要" not in m.get("content", "")
        ]

        if not prunable:
            return history

        # 使用 LLM 计算语义相关性
        semantic_scores = await self._compute_semantic_relevance(prunable, current_task)

        # 保留高相关性消息
        pruned = []
        for msg, score in zip(prunable, semantic_scores, strict=True):
            if score > self._config.relevance_threshold:
                pruned.append(msg)

        # 最小保留保护
        if len(pruned) < self._config.min_preserve_count:
            scored_msgs = sorted(
                zip(prunable, semantic_scores, strict=True),
                key=lambda x: x[1],
                reverse=True,
            )
            pruned = [m for m, s in scored_msgs[: self._config.min_preserve_count]]

        result = always_preserve + pruned

        if len(result) < len(history):
            filtered_count = len(history) - len(result)
            result.append(
                {
                    "role": "system",
                    "content": f"[语义裁剪: 已过滤 {filtered_count} 条，保留 {len(result)} 条]",
                }
            )

        return result

    def _extract_entities(self, task: str) -> list[str]:
        """提取任务关键实体

        包括: 文件路径、函数名、类名、关键词
        """
        entities: list[str] = []

        # 1. 文件路径 (如 "src/agent_loop.py")
        file_patterns = _RE_FILE_PATTERN.findall(task)
        for p in file_patterns:
            if "/" in p or "." in p and len(p) > 5:
                entities.append(p)

        # 2. 函数/类名 (如 "AgentLoop", "_execute_tool")
        # 匹配 CamelCase 和 snake_case
        code_patterns = _RE_CODE_PATTERN.findall(task)
        for p in code_patterns:
            if len(p) > 3 and p not in _RE_STOP_WORDS:
                entities.append(p)

        # 3. 关键词 (如 "重构", "优化", "bug", "fix")
        keywords = self._extract_keywords(task)
        entities.extend(keywords)

        # 去重
        return list(set(entities))

    def _extract_keywords(self, task: str) -> list[str]:
        """提取任务关键词"""
        # 技术关键词
        tech_keywords = [
            "bug",
            "fix",
            "error",
            "debug",
            "refactor",
            "重构",
            "optimize",
            "优化",
            "implement",
            "实现",
            "test",
            "测试",
            "create",
            "创建",
            "modify",
            "修改",
            "delete",
            "删除",
            "read",
            "读取",
            "write",
            "写入",
            "execute",
            "执行",
            "parse",
            "解析",
            "validate",
            "验证",
            "update",
            "更新",
            "import",
            "导入",
            "export",
            "导出",
            "search",
            "搜索",
            "find",
            "查找",
            "replace",
            "替换",
            "analyze",
            "分析",
        ]

        found = []
        task_lower = task.lower()
        for kw in tech_keywords:
            if kw.lower() in task_lower:
                found.append(kw)

        return found

    def _compute_relevance(
        self, history: list[dict[str, Any]], entities: list[str]
    ) -> list[float]:
        """计算相关性分数

        Args:
            history: 消息历史
            entities: 关键实体列表

        Returns:
            每条消息的相关性分数 (0.0 - 1.0)
        """
        scores: list[float] = []

        for msg in history:
            content = msg.get("content", "")
            role = msg.get("role", "")

            if not isinstance(content, str):
                scores.append(0.0)
                continue

            # 计算实体匹配度
            content_lower = content.lower()
            entity_matches = sum(1 for e in entities if e.lower() in content_lower)
            entity_score = entity_matches / max(len(entities), 1)

            # 获取角色权重
            role_weight = self._config.role_weights.get(role, 0.5)

            # 综合分数
            score = entity_score * role_weight
            scores.append(score)

        return scores

    async def _compute_semantic_relevance(
        self, history: list[dict[str, Any]], task: str
    ) -> list[float]:
        """语义相关性计算（使用 LLM）

        对于复杂任务，使用 LLM 评估相关性
        """
        scores: list[float] = []

        # 批量评估（避免多次调用）
        # 构建批量提示
        batch_prompt = self._build_batch_relevance_prompt(history, task)

        # 显式检查：调用此方法前已检查 gateway 和 model_id
        if self._gateway is None or self._model_id is None:
            raise RuntimeError(
                "ContextEngineering not properly initialized - "
                "gateway and model_id must be set before calling _evaluate_semantic_relevance"
            )

        try:
            response = await self._gateway.chat_completion(
                self._model_id, [{"role": "user", "content": batch_prompt}], tools=None
            )
            choices = response.get("choices", [])
            if not choices:
                logger.warning("Semantic relevance: LLM returned empty choices")
                entities = self._extract_entities(task)
                return self._compute_relevance(history, entities)
            result_text = choices[0].get("message", {}).get("content", "")
            if not result_text:
                entities = self._extract_entities(task)
                return self._compute_relevance(history, entities)

            # 解析分数
            scores = self._parse_relevance_scores(result_text, len(history))

        except Exception as e:
            logger.warning(f"Semantic relevance failed: {type(e).__name__}: {e}")
            # Fallback: 使用实体匹配
            entities = self._extract_entities(task)
            scores = self._compute_relevance(history, entities)

        return scores

    def _build_batch_relevance_prompt(
        self, history: list[dict[str, Any]], task: str
    ) -> str:
        """构建批量相关性评估提示"""
        messages_text = []
        for i, msg in enumerate(history):
            role = msg.get("role", "")
            content = msg.get("content", "")[:100]  # 限制长度
            messages_text.append(f"{i}: [{role}] {content}")

        return f"""评估以下消息与当前任务的相关性（0-1分）：

任务: {task}

消息列表:
{chr(10).join(messages_text[:20])}  # 最多 20 条

请输出每条消息的相关性分数，格式如下：
0: 0.8
1: 0.3
...

仅输出分数，无需解释。"""

    def _parse_relevance_scores(
        self, result_text: str, expected_count: int
    ) -> list[float]:
        """解析相关性分数"""
        scores: list[float] = []

        # 提取数字分数
        pattern = r"(\d+):\s*([\d.]+)"
        matches = re.findall(pattern, result_text)

        # 按索引排序
        indexed_scores = {}
        for idx_str, score_str in matches:
            try:
                idx = int(idx_str)
                score = float(score_str)
                if 0 <= score <= 1:
                    indexed_scores[idx] = score
            except ValueError:
                continue

        # 按顺序填充
        for i in range(expected_count):
            scores.append(indexed_scores.get(i, 0.5))  # 默认中等相关性

        return scores


class ContextEngineering:
    """上下文工程集成管理器

    协调渐进式压缩和智能裁剪：
    - 先裁剪（基于任务相关性）
    - 后压缩（基于容量使用率）

    使用流程:
    1. 创建实例，传入 Gateway 和 Session
    2. 调用 build_optimized_context() 获取优化后的上下文
    3. 发送给 LLM 推理
    """

    def __init__(
        self,
        gateway: "LLMGateway",
        model_id: str,
        compression_config: CompressionConfig | None = None,
        pruning_config: PruningConfig | None = None,
    ):
        """初始化上下文工程管理器

        Args:
            gateway: LLM Gateway 实例
            model_id: 模型 ID
            compression_config: 压缩配置
            pruning_config: 裁剪配置
        """
        self._gateway = gateway
        self._model_id = model_id

        self._compressor = ProgressiveContextCompressor(
            gateway, model_id, compression_config
        )
        self._pruner = IntelligentContextPruner(gateway, model_id, pruning_config)

        logger.info(f"ContextEngineering initialized: model={model_id}")

    def build_optimized_context(
        self,
        session: SessionEventStream,
        context_window: int,
        current_task: str | None = None,
        system_prompt: str | None = None,
        enable_pruning: bool = True,
    ) -> list[dict[str, Any]]:
        """构建优化后的上下文（同步版本）

        流程：
        1. 从 Session 构建完整历史
        2. 智能裁剪（可选，基于任务相关性）
        3. 渐进式压缩（基于容量使用率）

        Args:
            session: 事件流
            context_window: 上下文窗口大小
            current_task: 当前任务描述（用于裁剪）
            system_prompt: 系统提示
            enable_pruning: 是否启用裁剪

        Returns:
            优化后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._compressor._build_history_from_session(
            session, system_prompt
        )

        # 2. 智能裁剪（可选）
        if enable_pruning and current_task:
            pruned_history = self._pruner.prune_for_task(full_history, current_task)
        else:
            pruned_history = full_history

        # 3. 渐进式压缩
        # 注意：压缩器需要重新从 session 构建，因为裁剪可能改变了结构
        # 这里我们直接对 pruned_history 应用压缩策略
        compressed = self._apply_compression_to_pruned(
            pruned_history, context_window, system_prompt
        )

        logger.info(
            f"Context optimized: full={len(full_history)}, "
            f"pruned={len(pruned_history)}, final={len(compressed)}"
        )

        return compressed

    async def build_optimized_context_async(
        self,
        session: SessionEventStream,
        context_window: int,
        current_task: str | None = None,
        system_prompt: str | None = None,
        enable_pruning: bool = True,
        enable_semantic_pruning: bool = False,
    ) -> list[dict[str, Any]]:
        """构建优化后的上下文（异步版本，支持 LLM 摘要）

        Args:
            session: 事件流
            context_window: 上下文窗口大小
            current_task: 当前任务描述
            system_prompt: 系统提示
            enable_pruning: 是否启用裁剪
            enable_semantic_pruning: 是否启用语义裁剪（LLM）

        Returns:
            优化后的消息列表
        """
        # 1. 从 Session 构建完整历史
        full_history = self._compressor._build_history_from_session(
            session, system_prompt
        )

        # 2. 智能裁剪（可选）
        if enable_pruning and current_task:
            if enable_semantic_pruning:
                pruned_history = await self._pruner.prune_with_semantic_relevance(
                    full_history, current_task
                )
            else:
                pruned_history = self._pruner.prune_for_task(full_history, current_task)
        else:
            pruned_history = full_history

        # 3. 渐进式压缩（异步，支持 LLM 摘要）
        return await self._apply_compression_to_pruned_async(
            pruned_history, context_window, system_prompt
        )

    def _apply_compression_to_pruned(
        self,
        pruned_history: list[dict[str, Any]],
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """对已裁剪的历史应用压缩（同步）"""
        # 估算 Token
        current_tokens = self._compressor._estimate_tokens(pruned_history)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        # 根据使用率选择压缩层级
        config = self._compressor._config
        tier_2_threshold = config.tiers[CompressionTier.TIER_2_LIGHT].threshold
        tier_3_threshold = config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold

        if usage_ratio < tier_2_threshold:
            return self._compressor._apply_tier_1_only(pruned_history)
        if usage_ratio < tier_3_threshold:
            return self._compressor._apply_tier_1_and_2(pruned_history)
        return self._compressor._apply_all_tiers(pruned_history)

    async def _apply_compression_to_pruned_async(
        self,
        pruned_history: list[dict[str, Any]],
        context_window: int,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """对已裁剪的历史应用压缩（异步）"""
        current_tokens = self._compressor._estimate_tokens(pruned_history)
        usage_ratio = current_tokens / context_window if context_window > 0 else 0.0

        config = self._compressor._config
        tier_2_threshold = config.tiers[CompressionTier.TIER_2_LIGHT].threshold
        tier_3_threshold = config.tiers[CompressionTier.TIER_3_ABSTRACT].threshold

        if usage_ratio < tier_2_threshold:
            return self._compressor._apply_tier_1_only(pruned_history)
        if usage_ratio < tier_3_threshold:
            return await self._compressor._apply_tier_1_and_2_async(pruned_history)
        return await self._compressor._apply_all_tiers_async(pruned_history)

    def get_compressor(self) -> ProgressiveContextCompressor:
        """获取压缩器实例"""
        return self._compressor

    def get_pruner(self) -> IntelligentContextPruner:
        """获取裁剪器实例"""
        return self._pruner
