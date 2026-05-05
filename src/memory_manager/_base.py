"""MemoryManager 基础模块

单例模式实现和基础初始化
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from src.client import LLMGateway

from src.tools.long_term_archive import LongTermArchiveLayer
from src.tools.user_modeling import UserModelingLayer

logger = logging.getLogger(__name__)


def get_memory_root() -> Path:
    """获取记忆根目录（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().memory_dir
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "memory"


class MemoryManagerBase:
    """MemoryManager 基类 - 单例模式"""

    # 类属性（单例状态）
    _instance: MemoryManagerBase | None = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    # 实例属性类型声明
    _llm_gateway: LLMGateway | None
    _l4_user_modeling: UserModelingLayer
    _l5_archive: LongTermArchiveLayer
    _l1_path: Path
    _l2_path: Path
    _l3_path: Path

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        """单例模式 - 线程安全的双重检查锁定"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cast("Self", cls._instance)

    def _do_init(self, llm_gateway: LLMGateway | None = None) -> None:
        """执行初始化（内部方法）"""
        if self._initialized:
            return

        with MemoryManagerBase._lock:
            if self._initialized:
                return
            self._initialized = True

        self._llm_gateway = llm_gateway

        # 初始化各层
        self._l4_user_modeling = UserModelingLayer()
        self._l5_archive = LongTermArchiveLayer()

        # 设置 LLM Gateway
        if llm_gateway:
            self._l4_user_modeling.set_llm_gateway(llm_gateway)
            self._l5_archive.set_llm_gateway(llm_gateway)

        # L1-L3 路径（动态）
        memory_root = get_memory_root()
        self._l1_path = memory_root / "notes.md"
        self._l2_path = memory_root / "skills"
        self._l3_path = memory_root / "knowledge"

        logger.info("MemoryManager initialized with 5 layers")

    def set_llm_gateway(self, gateway: Any) -> None:
        """设置 LLM Gateway"""
        self._llm_gateway = gateway
        self._l4_user_modeling.set_llm_gateway(gateway)
        self._l5_archive.set_llm_gateway(gateway)

    def close(self) -> None:
        """关闭所有资源"""
        self._l4_user_modeling.close()
        self._l5_archive.close()
        MemoryManagerBase._instance = None
        MemoryManagerBase._initialized = False

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        if cls._instance:
            cls._instance.close()
        cls._instance = None
        cls._initialized = False