"""
Vision API 工具函数
配置路径、图像加载、模型映射、消息构建等通用工具
"""

import asyncio
import logging
from pathlib import Path

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger("seed_agent")

# ================= 配置常量 =================
VISION_MODEL = "bailian/qwen3.6-plus"
MAX_PIXELS = 1_440_000

# 模型映射
MODEL_MAP = {
    "claude": "anthropic/claude-3-5-sonnet-20241022",
    "openai": "openai/gpt-4o",
    "dashscope": "bailian/qwen3.6-plus",
}

# 延迟初始化的配置路径
DEFAULT_CONFIG_PATH: Path | None = None


def _get_config_path() -> Path:
    """获取配置文件路径（动态）"""
    try:
        from src.models import get_config_path

        return get_config_path()
    except ImportError:
        logger.debug("Using fallback config path: ~/.seed/config.json")
        return Path.home() / ".seed" / "config.json"
    except RuntimeError:
        logger.debug("PathsConfig not initialized, using fallback config path")
        return Path.home() / ".seed" / "config.json"


def _ensure_config_path() -> Path:
    """确保配置路径已初始化"""
    global DEFAULT_CONFIG_PATH
    if DEFAULT_CONFIG_PATH is None:
        DEFAULT_CONFIG_PATH = _get_config_path()
    return DEFAULT_CONFIG_PATH


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


def _run_vision_in_new_loop(
    gateway, model_id: str, messages: list, timeout: int
) -> dict:
    """在独立线程中创建新事件循环执行视觉分析"""
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