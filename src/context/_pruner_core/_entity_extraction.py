"""
实体提取模块

提供实体提取功能：
- _extract_entities: 提取任务关键实体
- _extract_keywords: 提取任务关键词

核心特性：
- 文件路径识别
- 函数/类名识别
- 技术关键词提取
"""

import logging

from src.context._config import get_code_pattern, get_file_pattern, get_stop_words

logger = logging.getLogger(__name__)


class EntityExtractionMixin:
    """实体提取功能 Mixin"""

    def _extract_entities(self, task: str) -> list[str]:
        """提取任务关键实体

        包括: 文件路径、函数名、类名、关键词
        """
        entities: list[str] = []

        # 1. 文件路径 (如 "src/agent_loop.py")
        file_patterns = get_file_pattern().findall(task)
        entities.extend(
            p for p in file_patterns if "/" in p or ("." in p and len(p) > 5)
        )

        # 2. 函数/类名 (如 "AgentLoop", "_execute_tool")
        code_patterns = get_code_pattern().findall(task)
        entities.extend(
            p for p in code_patterns if len(p) > 3 and p not in get_stop_words()
        )

        # 3. 关键词
        keywords = self._extract_keywords(task)
        entities.extend(keywords)

        # 去重
        return list(set(entities))

    def _extract_keywords(self, task: str) -> list[str]:
        """提取任务关键词"""
        tech_keywords = [
            "bug", "fix", "error", "debug", "refactor", "重构",
            "optimize", "优化", "implement", "实现", "test", "测试",
            "create", "创建", "modify", "修改", "delete", "删除",
            "read", "读取", "write", "写入", "execute", "执行",
            "parse", "解析", "validate", "验证", "update", "更新",
            "import", "导入", "export", "导出", "search", "搜索",
            "find", "查找", "replace", "替换", "analyze", "分析",
        ]

        task_lower = task.lower()
        return [kw for kw in tech_keywords if kw.lower() in task_lower]