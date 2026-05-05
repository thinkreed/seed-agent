"""
用户建模工具 wrapper

调用 user_modeling 模块的 L4 用户偏好管理功能。

核心功能（黑格尔辩证式进化）：
- _observe_user_preference: 观察用户偏好证据
- _get_user_preference: 获取用户偏好（带上下文）
- _get_user_profile_summary: 获取用户画像摘要
- _update_user_model: 触发辩证式更新
- _list_user_preferences: 列出所有偏好
"""

import logging

logger = logging.getLogger(__name__)


def _observe_user_preference(
    key: str, value: str, context: str | None = None, confidence: float = 0.8
) -> str:
    """
    观察用户偏好证据

    Args:
        key: 偏好键 (如 "coffee", "work_style")
        value: 偏好值
        context: 观察上下文 (如 "周三下午")
        confidence: 置信度 (0.0-1.0)

    Returns:
        观察记录状态

    Example:
        observe_user_preference("coffee", "美式", confidence=0.9)
        observe_user_preference("coffee", "拿铁", context="周三下午", confidence=0.85)
    """
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
        return f"Error observing preference: {type(e).__name__}: {str(e)[:100]}"


def _get_user_preference(key: str, context: str | None = None) -> str:
    """
    获取用户偏好（基于上下文）

    Args:
        key: 偏好键
        context: 当前上下文 (用于检查例外情况)

    Returns:
        基于上下文的偏好值和推理说明

    Example:
        get_user_preference("coffee") -> "美式 (常规偏好)"
        get_user_preference("coffee", "周三下午") -> "拿铁 (例外情况: 周三下午)"
    """
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
        return f"Error getting preference: {type(e).__name__}: {str(e)[:100]}"


def _get_user_profile_summary() -> str:
    """
    获取用户画像完整摘要

    Returns:
        所有偏好的摘要，包括例外情况

    Example:
        用户画像摘要:
        - coffee: 平时 美式, 例外情况 周三下午: 拿铁
        - work_style: 深度工作模式
    """
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.get_user_profile_summary()
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error getting profile: {type(e).__name__}: {str(e)[:100]}"


def _update_user_model() -> str:
    """
    触发用户模型辩证式更新

    注意: 此函数为异步操作，在同步环境中返回提示信息

    Returns:
        更新提示信息 (实际更新需要在异步环境中执行)
    """
    return (
        "提示: 用户模型辩证式更新需要异步执行。\n"
        "请使用 MemoryManager.update_user_model() 在异步环境中调用。\n"
        "流程: 检测矛盾 -> 内部推理 -> 升级模型 (不覆盖)"
    )


def _list_user_preferences() -> str:
    """
    列出所有用户偏好

    Returns:
        所有偏好的键值列表
    """
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
        return f"Error listing preferences: {type(e).__name__}: {str(e)[:100]}"