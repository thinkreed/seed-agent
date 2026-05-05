"""
渐进式上下文压缩模块

三层压缩策略：
- Tier 1: 最新 5 轮完整保留 (Full)
- Tier 2: 稍旧 10 轮轻量总结 (Light Summary) - 50% 容量时触发
- Tier 3: 更早历史简短摘要 (Abstract) - 75% 容量时触发

核心特性：
- 渐进信息损失，不丢失原始数据（Session 保留）
- 根据上下文使用率动态选择压缩层级
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.context._config import CompressionConfig, CompressionTier
from src.session_event_stream import EventType, SessionEventStream

logger = logging.getLogger(__name__)


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

        key_sentences = [
            sentence[:max_len]
            for sentence in sentences
            if any(kw in sentence for kw in keywords)
        ]

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