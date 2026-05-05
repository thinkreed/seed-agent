"""
相关性计算模块

提供相关性计算功能：
- _compute_relevance: 计算实体匹配相关性
- _compute_semantic_relevance: 使用 LLM 计算语义相关性
- _build_batch_relevance_prompt: 构建批量评估提示
- _parse_relevance_scores: 解析相关性分数

核心特性：
- 实体匹配度计算
- 角色权重加权
- LLM 语义评估（可选）
"""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


class RelevanceMixin:
    """相关性计算功能 Mixin"""

    _gateway: "LLMGateway | None"
    _model_id: str | None
    _config: Any

    def _compute_relevance(
        self, history: list[dict[str, Any]], entities: list[str]
    ) -> list[float]:
        """计算相关性分数"""
        scores: list[float] = []

        for msg in history:
            content = msg.get("content", "")
            role = msg.get("role", "")

            if not isinstance(content, str):
                scores.append(0.0)
                continue

            content_lower = content.lower()
            entity_matches = sum(1 for e in entities if e.lower() in content_lower)
            entity_score = entity_matches / max(len(entities), 1)

            role_weight = self._config.role_weights.get(role, 0.5)

            score = entity_score * role_weight
            scores.append(score)

        return scores

    async def _compute_semantic_relevance(
        self, history: list[dict[str, Any]], task: str
    ) -> list[float]:
        """语义相关性计算（使用 LLM）"""
        scores: list[float] = []

        batch_prompt = self._build_batch_relevance_prompt(history, task)

        if self._gateway is None or self._model_id is None:
            raise RuntimeError("ContextEngineering not properly initialized")

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

            scores = self._parse_relevance_scores(result_text, len(history))

        except Exception as e:
            logger.warning(f"Semantic relevance failed: {type(e).__name__}: {e}")
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
            content = msg.get("content", "")[:100]
            messages_text.append(f"{i}: [{role}] {content}")

        return f"""评估以下消息与当前任务的相关性（0-1分）：

任务: {task}

消息列表:
{chr(10).join(messages_text[:20])}

请输出每条消息的相关性分数，格式如下：
0: 0.8
1: 0.3
...

仅输出分数，无需解释。"""

    def _parse_relevance_scores(
        self, result_text: str, expected_count: int
    ) -> list[float]:
        """解析相关性分数"""
        pattern = r"(\d+):\s*([\d.]+)"
        matches = re.findall(pattern, result_text)

        indexed_scores = {}
        for idx_str, score_str in matches:
            try:
                idx = int(idx_str)
                score = float(score_str)
                if 0 <= score <= 1:
                    indexed_scores[idx] = score
            except ValueError:
                continue

        return [indexed_scores.get(i, 0.5) for i in range(expected_count)]