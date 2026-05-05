"""
重试逻辑模块

提供:
- should_continue_retry: 判断是否应该继续重试
- get_retry_wait_time: 计算重试等待时间（支持 Retry-After + Jitter）
"""

import asyncio
import logging
import random

logger = logging.getLogger("seed_agent")


def should_continue_retry(attempt: int, max_retries: int = 3) -> bool:
    """判断是否应该继续重试

    Args:
        attempt: 当前重试次数 (0-based)
        max_retries: 最大重试次数

    Returns:
        是否应该继续重试
    """
    return attempt < max_retries - 1


def get_retry_wait_time(attempt: int, error: Exception | None = None) -> float:
    """计算重试等待时间 (支持 Retry-After 头解析 + Jitter)

    Args:
        attempt: 当前重试次数 (0-based)
        error: 触发重试的异常（可选）

    Returns:
        等待时间（秒），上限 60 秒防止过度阻塞
    """
    # 1. Check for Retry-After header (common in 429 Rate Limit errors)
    if error and hasattr(error, "response") and error.response is not None:
        retry_after = error.response.headers.get("retry-after")
        if retry_after:
            try:
                wait_time = int(retry_after)
                # Cap at 60s to prevent excessive blocking if server requests long wait
                return min(float(wait_time), 60.0)
            except (ValueError, TypeError) as e:
                logger.debug(f"Invalid Retry-After header '{retry_after}': {e}")

    # 2. Default exponential backoff with Jitter: 1s, 2s, 4s (+/- 20%)
    # Jitter prevents "thundering herd" problem
    # Note: random.uniform is used for retry timing, not cryptographic purposes
    base_wait = 2**attempt
    jitter = random.uniform(-0.2, 0.2) * base_wait
    # 确保等待时间非负且有最小值
    return max(0.5, base_wait + jitter)


async def sleep_with_retry_wait_time(attempt: int, error: Exception | None = None) -> None:
    """使用计算的重试等待时间进行 sleep

    Args:
        attempt: 当前重试次数 (0-based)
        error: 触发重试的异常（可选）
    """
    wait_time = get_retry_wait_time(attempt, error)
    logger.warning(f"Retry {attempt + 1}/3 after {wait_time}s: {error}")
    await asyncio.sleep(wait_time)
