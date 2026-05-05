"""
智能上下文裁剪模块

根据当前任务相关性裁剪不相关历史：
- 实体提取：文件路径、函数名、类名、关键词
- 相关性计算：entity_matches + 角色权重
- 语义相关性：使用 LLM 评估（可选）

核心特性：
- 保留高相关性消息
- 添加裁剪说明
- 最小保留数量保护
"""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.context._config import (
    PruningConfig,
    get_code_pattern,
    get_file_pattern,
    get_stop_words,
)

logger = logging.getLogger(__name__)


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
            if m["role"] != "system" and "摘要" not in m.get("content", "")
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
            if m["role"] != "system" and "摘要" not in m.get("content", "")
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
        file_patterns = get_file_pattern().findall(task)
        entities.extend(
            p
            for p in file_patterns
            if "/" in p or ("." in p and len(p) > 5)
        )

        # 2. 函数/类名 (如 "AgentLoop", "_execute_tool")
        # 匹配 CamelCase 和 snake_case
        code_patterns = get_code_pattern().findall(task)
        entities.extend(
            p for p in code_patterns if len(p) > 3 and p not in get_stop_words()
        )

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

        task_lower = task.lower()
        return [kw for kw in tech_keywords if kw.lower() in task_lower]

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
        return [indexed_scores.get(i, 0.5) for i in range(expected_count)]