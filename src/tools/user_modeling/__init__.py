"""
L4 用户建模层 - 黑格尔辩证式进化

核心理念:
- 不是一次判断就定终身，允许用户改变、允许情况复杂
- 通过不断观察、思考、调整，越来越懂真实的用户
- 升级而非覆盖：保留例外情况和复杂偏好

架构:
- _db.py: 数据库管理
- _observation.py: 观察机制
- _dialectic.py: 辩证更新
- _upgrade.py: 模型升级
- _retrieval.py: 检索查询

使用方法:
    from src.tools.user_modeling import UserModelingLayer
    
    layer = UserModelingLayer()
    layer.observe("preference", {"key": "coffee", "value": "拿铁"})
    await layer.dialectical_update()
    pref = layer.get_user_preference("coffee")
"""

import logging
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from src.client import LLMGateway

from ._db import get_db
from ._dialectic import get_dialectic_engine
from ._observation import get_observation_manager
from ._retrieval import get_retrieval_manager
from ._upgrade import get_upgrade_engine

logger = logging.getLogger(__name__)

# 导出子模块供外部使用
__all__ = [
    "UserModelingLayer",
    "get_db",
    "get_dialectic_engine",
    "get_observation_manager",
    "get_retrieval_manager",
    "get_upgrade_engine",
]


class UserModelingLayer:
    """L4 用户建模 - 黑格尔辩证式进化

    组合各子模块提供统一接口:
    1. observe(): 观察用户行为和偏好
    2. dialectical_update(): 辩证式更新模型
    3. get_user_preference(): 获取基于上下文的偏好
    4. get_user_profile_summary(): 获取用户画像摘要
    """

    _instance: "UserModelingLayer | None" = None

    def __new__(cls) -> Self:
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        db_path: str | None = None,
        llm_gateway: "LLMGateway | None" = None,
    ):
        # 单例已初始化则跳过
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self._db = get_db()
        self._observation = get_observation_manager()
        self._dialectic = get_dialectic_engine()
        self._upgrade = get_upgrade_engine()
        self._retrieval = get_retrieval_manager()

        if llm_gateway:
            self._dialectic.set_llm_gateway(llm_gateway)

    def set_llm_gateway(self, gateway: "LLMGateway") -> None:
        """设置 LLM Gateway"""
        self._dialectic.set_llm_gateway(gateway)

    def close(self) -> None:
        """关闭数据库连接"""
        self._db.close()

    # === 观察 ===

    def observe(
        self,
        evidence_type: str,
        data: dict[str, Any],
        context: str | None = None,
        confidence: float = 0.8,
    ) -> str:
        """观察新证据"""
        return self._observation.observe(evidence_type, data, context, confidence)

    def observe_from_interaction(self, interaction: dict[str, Any]) -> list[str]:
        """从用户交互中提取观察"""
        return self._observation.observe_from_interaction(interaction)

    # === 辩证式更新 ===

    async def dialectical_update(self) -> dict[str, Any]:
        """辩证式更新

        流程:
        1. 检测新证据与旧模型矛盾
        2. 内部推理讨论
        3. 升级用户模型

        Returns:
            更新报告
        """
        # 获取未处理的观察
        unprocessed = self._observation.get_unprocessed_observations()

        if not unprocessed:
            return {"status": "no_new_observations", "conflicts": [], "updates": []}

        # 检测矛盾
        conflicts = await self._dialectic.detect_conflicts(unprocessed)

        if not conflicts:
            # 无矛盾，直接强化
            await self._upgrade.reinforce_model(unprocessed)
            self._observation.mark_observations_processed(unprocessed)
            return {"status": "reinforced", "conflicts": [], "updates": unprocessed}

        # 内部推理
        resolution = await self._dialectic.reason_about_conflicts(conflicts)

        # 升级模型
        updates = self._upgrade.upgrade_model(resolution)

        # 标记已处理
        self._observation.mark_observations_processed(unprocessed)

        # 记录历史
        self._dialectic.record_dialectical_history(conflicts, resolution, updates)

        return {
            "status": "upgraded",
            "conflicts": conflicts,
            "resolution": resolution,
            "updates": updates,
        }

    # === 检索 ===

    def get_user_preference(
        self, key: str, context: str | None = None
    ) -> dict[str, Any]:
        """获取用户偏好"""
        return self._retrieval.get_user_preference(key, context)

    def get_user_profile_summary(self) -> str:
        """获取用户画像摘要"""
        return self._retrieval.get_user_profile_summary()

    def get_all_preferences(self) -> dict[str, dict[str, Any]]:
        """获取所有偏好"""
        return self._retrieval.get_all_preferences()

    def get_dialectical_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取辩证进化历史"""
        return self._retrieval.get_dialectical_history(limit)

    def clear_preference(self, key: str) -> str:
        """清除特定偏好"""
        return self._retrieval.clear_preference(key)

    def clear_all_observations(self) -> str:
        """清除所有观察记录"""
        return self._observation.clear_all_observations()