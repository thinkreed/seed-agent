"""
Ralph Loop 完成验证模块

处理各种完成验证类型的检查逻辑。
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.ralph_core._completion_exec import CompletionExecChecker
from src.ralph_core._types import CompletionType

logger = logging.getLogger("seed_agent.ralph")


class CompletionChecker:
    """完成验证器"""

    def __init__(self) -> None:
        self._exec_checker = CompletionExecChecker()

    async def check_completion(
        self,
        completion_type: CompletionType,
        criteria: dict[str, Any] | None,
    ) -> bool:
        """外部完成验证（核心机制）"""
        validators = {
            CompletionType.TEST_PASS: self._exec_checker.check_test_pass,
            CompletionType.FILE_EXISTS: self._check_file_exists,
            CompletionType.MARKER_FILE: self._check_marker_file,
            CompletionType.GIT_CLEAN: self._exec_checker.check_git_clean,
            CompletionType.CUSTOM_CHECK: self._check_custom,
        }

        validator = validators.get(completion_type)
        if validator:
            try:
                if asyncio.iscoroutinefunction(validator):
                    result = await validator(criteria)
                else:
                    result = validator(criteria)
                if result:
                    logger.info(f"Completion verified: {completion_type}")
                return result
            except Exception as e:
                logger.warning(f"Completion check failed: {type(e).__name__}: {e}")
                return False
        return False

    def _check_file_exists(self, criteria: dict[str, Any] | None) -> bool:
        """检查目标文件存在"""
        if not criteria:
            return False
        files = criteria.get("files", [])
        if not files:
            return False

        all_exist = all(Path(f).exists() for f in files)
        if all_exist:
            logger.info(f"All target files exist: {files}")
        return all_exist

    def _check_marker_file(self, criteria: dict[str, Any] | None) -> bool:
        """检查完成标志文件"""
        if not criteria:
            return False
        marker_path = Path(criteria.get("marker_path", ".seed/completion_marker"))
        marker_content = criteria.get("marker_content", "DONE")

        try:
            if marker_path.exists():
                content = marker_path.read_text(encoding="utf-8").strip()
                if content == marker_content:
                    logger.info(f"Marker file verified: {marker_path}")
                    if criteria.get("cleanup_marker", True):
                        try:
                            marker_path.unlink()
                        except OSError:
                            pass
                    return True
        except Exception as e:
            logger.warning(f"Failed to check marker file: {e}")
        return False

    async def _check_custom(self, criteria: dict[str, Any] | None) -> bool:
        """自定义验证函数"""
        if not criteria:
            return False
        checker = criteria.get("checker")
        if checker and callable(checker):
            try:
                if asyncio.iscoroutinefunction(checker):
                    result = await checker()
                else:
                    result = checker()
                logger.info(f"Custom check result: {result}")
                return bool(result)
            except Exception as e:
                logger.warning(f"Custom check failed: {type(e).__name__}: {e}")
                return False
        return False

    def _parse_test_pass_rate(self, output: str | bytes) -> float:
        """解析测试输出获取通过率（委托给 exec_checker）"""
        return self._exec_checker._parse_test_pass_rate(output)