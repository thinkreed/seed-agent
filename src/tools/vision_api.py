"""
Vision API Helper - 视觉识别基础模块
支持: 窗口截图, 图像编码, 调用多模态大模型 (Claude/OpenAI/DashScope)
"""

import base64
import io
import logging
import os
from pathlib import Path

try:
    from PIL import Image, ImageGrab

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger("seed_agent")

# ================= 配置 =================
VISION_MODEL = os.getenv("VISION_MODEL", "bailian/qwen3.6-plus")
MAX_PIXELS = 1_440_000  # 限制图像像素以节省 Token
DEFAULT_CONFIG_PATH = os.path.join(Path.home(), ".seed", "config.json")

# 模型映射
MODEL_MAP = {
    "claude": "anthropic/claude-3-5-sonnet-20241022",
    "openai": "openai/gpt-4o",
    "dashscope": "bailian/qwen3.6-plus",
}


def capture_window(hwnd=None) -> "Image.Image | None":
    """
    截取指定窗口或全屏图像
    Args:
        hwnd: 窗口句柄 (Windows)
    Returns:
        PIL Image 对象
    """
    if not HAS_PIL:
        logger.error("Pillow not installed. pip install Pillow")
        return None

    try:
        img = ImageGrab.grab()
        return _resize_if_needed(img, MAX_PIXELS)
    except OSError:
        logger.exception("Screen capture failed")
        return None


def _resize_if_needed(img: "Image.Image", max_pixels: int) -> "Image.Image":
    """如果像素超过限制，则等比缩放"""
    w, h = img.size
    if w * h > max_pixels:
        ratio = (max_pixels / (w * h)) ** 0.5
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img


def image_to_base64(img: "Image.Image", image_format: str = "PNG") -> str:
    """将图像转换为 Base64 字符串"""
    buffered = io.BytesIO()
    img.save(buffered, format=image_format)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


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

    # 构建 OpenAI 兼容的多模态消息
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64_img}",
                        "detail": "auto",
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    cfg_path = config_path or DEFAULT_CONFIG_PATH
    import asyncio

    if not await asyncio.to_thread(Path(cfg_path).exists):
        return f"Error: Config file not found at {cfg_path}"

    try:
        # 通过 LLMGateway 调用
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


def _load_image(image) -> tuple:
    """Load image from path or return as-is. Returns (image, error)."""
    if isinstance(image, str):
        if not HAS_PIL:
            return None, "Error: Pillow not installed"
        try:
            return Image.open(image), None
        except (OSError, FileNotFoundError) as e:
            return None, f"Error loading image: {e}"
    return image, None


def _resolve_vision_model(backend: str) -> str:
    """Map backend name to model ID."""
    return MODEL_MAP.get(backend.lower(), VISION_MODEL)


def _build_vision_messages(b64_img: str, prompt: str) -> list:
    """Build OpenAI-compatible multimodal messages."""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64_img}",
                        "detail": "auto",
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]


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
    - 在异步环境中：使用 asyncio.run_coroutine_threadsafe() 或创建任务
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
        import asyncio

        from src.client import LLMGateway, RequestPriority

        if not os.path.exists(DEFAULT_CONFIG_PATH):
            return f"Error: Config not found at {DEFAULT_CONFIG_PATH}"

        gateway = LLMGateway(DEFAULT_CONFIG_PATH)

        # 智能检测当前是否在异步事件循环中
        try:
            asyncio.get_running_loop()  # 检测是否在异步环境中
            # 已在异步环境中：使用线程池执行避免阻塞当前循环
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    _run_vision_in_new_loop, gateway, model_id, messages, timeout
                )
                result = future.result(timeout=timeout + 5)  # 额外 5 秒缓冲
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


def _run_vision_in_new_loop(
    gateway, model_id: str, messages: list, timeout: int
) -> dict:
    """在独立线程中创建新事件循环执行视觉分析"""
    import asyncio

    from src.client import RequestPriority

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            gateway.chat_completion(
                model_id=model_id,
                messages=messages,
                priority=RequestPriority.HIGH,
                max_tokens=2048,
                timeout=timeout,
            )
        )
    finally:
        loop.close()
        asyncio.set_event_loop(None)


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    img = capture_window()
    if img is not None:
        print(f"Captured image: {img.size}")

        async def test(captured_img: "Image.Image"):
            result = await analyze_image_async(captured_img, "Describe this screen in detail")
            print(f"Result: {result}")

        asyncio.run(test(img))
    else:
        print("Failed to capture screen")
