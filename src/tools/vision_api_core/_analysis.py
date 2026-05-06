"""Vision API 图像分析模块 - 异步/同步视觉分析函数"""

import asyncio
import concurrent.futures
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

from ._capture import _resize_if_needed, image_to_base64
from ._utils import (
    DEFAULT_CONFIG_PATH,
    VISION_MODEL,
    _build_vision_messages,
    _ensure_config_path,
    _load_image,
    _resolve_vision_model,
    _run_vision_in_new_loop,
)

logger = logging.getLogger("seed_agent")


async def analyze_image_async(
    image: "Image.Image",
    prompt: str,
    model_id: str | None = None,
    config_path: str | None = None,
) -> str:
    """
    异步分析图像 - 通过 LLMGateway 调用多模态模型

    Args:
        image: PIL Image 对象
        prompt: 分析提示词
        model_id: 模型 ID (格式: provider/model)，默认 VISION_MODEL
        config_path: 配置文件路径，默认 ~/.seed/config.json

    Returns:
        模型响应文本
    """
    b64_img = image_to_base64(image)
    target_model = model_id or VISION_MODEL
    messages = _build_vision_messages(b64_img, prompt)
    cfg_path = str(config_path or DEFAULT_CONFIG_PATH)

    if not await asyncio.to_thread(Path(cfg_path).exists):
        return f"Error: Config file not found at {cfg_path}"

    try:
        from src.client import LLMGateway, RequestPriority

        gateway = LLMGateway(cfg_path)
        result = await gateway.chat_completion(
            model_id=target_model,
            messages=messages,
            priority=RequestPriority.HIGH,
            max_tokens=2048,
        )
        content = result.get("content", "")
        logger.info(f"Vision analysis completed, content length: {len(content)}")
        return content

    except (OSError, RuntimeError, ValueError) as e:
        error_msg = f"Vision API call failed: {type(e).__name__}: {e}"
        logger.exception("Vision API call failed")
        return f"Error: {error_msg}"


def ask_vision(
    image,
    prompt: str = "Describe this image",
    backend: str = "claude",
    timeout: int = 60,
    max_pixels: int = 1_440_000,
) -> str:
    """
    同步视觉分析包装器 (适用于 Skill 调用)

    自动检测运行环境：
    - 在异步环境中：使用线程池执行避免阻塞当前循环
    - 在同步环境中：创建新事件循环执行

    Args:
        image: 文件路径 (str) 或 PIL Image 对象
        prompt: 分析提示词
        backend: 提供商 (claude/openai/dashscope)
        timeout: 超时秒数
        max_pixels: 最大像素限制

    Returns:
        分析结果文本
    """
    img, err = _load_image(image)
    if err:
        return err

    img = _resize_if_needed(img, max_pixels)
    b64_img = image_to_base64(img)
    model_id = _resolve_vision_model(backend)
    messages = _build_vision_messages(b64_img, prompt)

    try:
        from src.client import LLMGateway, RequestPriority

        config_path = _ensure_config_path()
        if not config_path.exists():
            return f"Error: Config not found at {config_path}"

        gateway = LLMGateway(str(config_path))

        # 智能检测当前是否在异步事件循环中
        try:
            asyncio.get_running_loop()
            # 已在异步环境中：使用线程池执行避免阻塞当前循环
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    _run_vision_in_new_loop, gateway, model_id, messages, timeout
                )
                result = future.result(timeout=timeout + 5)
                return result.get("content", "No content returned")
        except RuntimeError:
            # 不在异步环境中：创建新事件循环
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    gateway.chat_completion(
                        model_id=model_id,
                        messages=messages,
                        priority=RequestPriority.HIGH,
                        max_tokens=2048,
                        timeout=timeout,
                    )
                )
                return result.get("content", "No content returned")
            finally:
                loop.close()

    except concurrent.futures.TimeoutError:
        return f"Error: Vision API call timed out ({timeout}s)"
    except ImportError as e:
        return f"Error: Missing dependency: {e}"
    except (OSError, RuntimeError, ValueError) as e:
        error_msg = f"Vision API error: {type(e).__name__}: {e}"
        logger.exception("Vision API error")
        return error_msg