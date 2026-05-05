"""
用户建模 Wrapper 模块

提供 L4 用户建模工具 wrapper：
- _observe_user_preference: 观察用户偏好
- _get_user_preference: 获取用户偏好
- _get_user_profile_summary: 获取画像摘要
- _update_user_model: 更新用户模型
- _list_user_preferences: 列出用户偏好

核心特性：
- 黑格尔辩证式进化
- 上下文感知偏好获取
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _observe_user_preference(
    key: str, value: str, context: str | None = None, confidence: float = 0.8
) -> str:
    """观察用户偏好证据"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.observe(
            evidence_type="preference",
            data={"key": key, "value": value},
            context=context,
            confidence=confidence,
        )
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


def _get_user_preference(key: str, context: str | None = None) -> str:
    """获取用户偏好"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        result = user_model.get_user_preference(key, context)

        output = f"用户偏好 '{key}':\n"
        output += f"- 值: {result['value']}\n"
        output += f"- 原因: {result['reason']}\n"
        output += f"- 置信度: {result['confidence']:.2f}\n"
        return output
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


def _get_user_profile_summary() -> str:
    """获取用户画像完整摘要"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.get_user_profile_summary()
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


def _update_user_model() -> str:
    """触发用户模型辩证式更新"""
    return (
        "提示: 用户模型辩证式更新需要异步执行。\n"
        "请使用 MemoryManager.update_user_model() 在异步环境中调用。\n"
        "流程: 检测矛盾 -> 内部推理 -> 升级模型 (不覆盖)"
    )


def _list_user_preferences() -> str:
    """列出所有用户偏好"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        preferences = user_model.get_all_preferences()

        if not preferences:
            return "无用户偏好记录"

        output = "用户偏好列表:\n"
        for key, pref_data in preferences.items():
            usual = pref_data.get("usual", "未知")
            exceptions = pref_data.get("exceptions", {})
            confidence = pref_data.get("confidence", 0.0)
            output += f"\n- {key}: {usual} (置信度 {confidence:.2f})\n"
            if exceptions:
                for exc_key, exc_val in exceptions.items():
                    if exc_key != "previously":
                        output += f"  例外 [{exc_key}]: {exc_val.get('value', '未知')}\n"
        return output
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


__all__ = [
    "_observe_user_preference",
    "_get_user_preference",
    "_get_user_profile_summary",
    "_update_user_model",
    "_list_user_preferences",
]