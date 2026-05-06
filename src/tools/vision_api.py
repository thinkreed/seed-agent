"""
Vision API Helper - 视觉识别基础模块
支持: 窗口截图, 图像编码, 调用多模态大模型 (Claude/OpenAI/DashScope)

公共 API 从 vision_api_core 子模块导出，保持向后兼容。
"""

# 从子模块导入所有公共 API
from src.tools.vision_api_core import (
    DEFAULT_CONFIG_PATH,
    HAS_PIL,
    MAX_PIXELS,
    MODEL_MAP,
    VISION_MODEL,
    _ensure_config_path,
    _get_config_path,
    analyze_image_async,
    ask_vision,
    capture_window,
    image_to_base64,
)

__all__ = [
    # 公共 API
    "capture_window",
    "image_to_base64",
    "analyze_image_async",
    "ask_vision",
    # 配置常量
    "VISION_MODEL",
    "MAX_PIXELS",
    "MODEL_MAP",
    "HAS_PIL",
    # 配置函数
    "DEFAULT_CONFIG_PATH",
    "_get_config_path",
    "_ensure_config_path",
]

if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    img = capture_window()
    if img is not None:
        logger.info(f"Captured image: {img.size}")

        async def test(captured_img):
            result = await analyze_image_async(
                captured_img, "Describe this screen in detail"
            )
            logger.info(f"Result: {result}")

        import asyncio

        asyncio.run(test(img))
    else:
        logger.warning("Failed to capture screen")