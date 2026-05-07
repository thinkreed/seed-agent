"""
Vision API Core - 视觉识别核心模块

子模块：
- _utils: 配置路径、模型映射、消息构建等工具函数
- _capture: 窗口截图、图像缩放、Base64 编码
- _analysis: 异步/同步视觉分析函数

公共 API:
- capture_window: 截取屏幕图像
- image_to_base64: 图像转 Base64
- analyze_image_async: 异步分析图像
- ask_vision: 同步视觉分析包装器
"""

from ._analysis import analyze_image_async, ask_vision
from ._capture import capture_window, image_to_base64
from ._utils import (
    DEFAULT_CONFIG_PATH,
    HAS_PIL,
    MAX_PIXELS,
    MODEL_MAP,
    VISION_MODEL,
    _ensure_config_path,
    _get_config_path,
)

__all__ = [
    # 配置函数
    "DEFAULT_CONFIG_PATH",
    "HAS_PIL",
    "MAX_PIXELS",
    "MODEL_MAP",
    # 配置常量
    "VISION_MODEL",
    "_ensure_config_path",
    "_get_config_path",
    "analyze_image_async",
    "ask_vision",
    # 公共 API
    "capture_window",
    "image_to_base64",
]