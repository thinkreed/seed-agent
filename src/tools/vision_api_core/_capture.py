"""
Vision API 图像捕获模块
窗口截图、图像缩放、Base64 编码
"""

import base64
import io
import logging
from typing import TYPE_CHECKING

try:
    from PIL import Image, ImageGrab

    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    if not TYPE_CHECKING:
        Image = None

from ._utils import MAX_PIXELS

logger = logging.getLogger("seed_agent")


def capture_window(hwnd=None) -> "Image.Image | None":
    """
    截取指定窗口或全屏图像

    Args:
        hwnd: 窗口句柄 (Windows，暂未使用)

    Returns:
        PIL Image 对象，失败返回 None
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