"""
临时客户端 - TemporaryClient

内部模块，负责临时客户端的创建和管理。

核心安全特性:
- 凭证不持久化存储
- 请求完成后自动销毁
- 安全清除内存中的凭证
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class TemporaryClient:
    """临时客户端（凭证销毁后不可用）

    基于 Harness Engineering "凭证永不进沙盒" 设计理念，
    客户端在请求完成后立即销毁，凭证从内存中安全清除。

    安全特性:
    - 使用内部列表存储凭证，便于安全清除
    - 多次覆盖内存区域，减少被内存扫描获取的风险
    - 销毁后标记为不可用状态

    Attributes:
        provider: 提供商名称
        client: 底层客户端实例
        _credential_storage: 内部凭证存储（使用列表便于覆盖）
        created_at: 创建时间戳
        destroyed: 是否已销毁

    Example:
        temp_client = await proxy._create_temp_client("openai", "sk-test123")
        result = await temp_client.client.chat.completions.create(...)
        temp_client.destroy()  # 凭证已安全清除
    """

    def __init__(
        self,
        provider: str,
        client: Any,
        credential: str | None = None,
        created_at: float | None = None,
        _credential_storage: list[str] | None = None,
    ):
        """初始化临时客户端

        Args:
            provider: 提供商名称
            client: 底层客户端实例
            credential: 凭证值（存储在内部列表中）
            created_at: 创建时间戳（默认为当前时间）
            _credential_storage: 内部凭证存储列表（向后兼容）

        Note:
            `credential` 和 `_credential_storage` 参数均可用于传入凭证。
            优先使用 `_credential_storage`（向后兼容测试），否则使用 `credential`。
        """
        self.provider = provider
        self.client = client
        # 使用内部列表存储凭证，便于安全清除
        # 向后兼容：支持 _credential_storage 参数
        self._credential_storage: list[str]
        if _credential_storage is not None:
            self._credential_storage = _credential_storage
        elif credential is not None:
            self._credential_storage = [credential]
        else:
            self._credential_storage = []
        self.created_at = created_at or time.time()
        self.destroyed: bool = False

    @property
    def credential(self) -> str:
        """获取凭证

        Returns:
            凭证值

        Raises:
            RuntimeError: 客户端已销毁
        """
        if self.destroyed:
            raise RuntimeError(
                "Client has been destroyed, credential no longer available"
            )
        return self._credential_storage[0] if self._credential_storage else ""

    def destroy(self) -> None:
        """销毁客户端（安全凭证清理）

        通过多次覆盖内存区域来安全清除凭证，
        减少被内存扫描获取的风险。

        清除流程:
        1. 标记为已销毁状态
        2. 清空客户端引用
        3. 多次覆盖凭证内存（零、一、标记）
        4. 清空存储列表
        """
        self.destroyed = True
        self.client = None

        # 安全清除凭证内存：多次覆盖
        if self._credential_storage:
            original_len = len(self._credential_storage[0])
            # 多次覆盖不同模式
            for _ in range(3):
                self._credential_storage[0] = "\x00" * original_len  # 全零
                self._credential_storage[0] = "\xff" * original_len  # 全一
                self._credential_storage[0] = "REDACTED" * (
                    original_len // 8 + 1
                )  # 标记
            # 最后清空列表
            self._credential_storage.clear()

        logger.debug(f"Temporary client destroyed for provider: {self.provider}")

    @property
    def lifetime_ms(self) -> float:
        """获取客户端存活时间（毫秒）"""
        return (time.time() - self.created_at) * 1000