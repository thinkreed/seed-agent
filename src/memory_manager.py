"""统一记忆管理器 - 五层架构集成

重构版本：原大文件已拆分为多个小模块
此文件保留为向后兼容的导入入口

详细文档请参阅 memory_manager/__init__.py 和子模块

模块结构:
- memory_manager/_base.py: 单例模式、基础初始化 (~90 行)
- memory_manager/_layers.py: L1-L5 层级访问 (~90 行)
- memory_manager/_search.py: 跨层搜索 (~110 行)
- memory_manager/_operations.py: 用户观察、会话归档 (~90 行)

总计: 4 个模块，每个均 < 150 行
"""

# 向后兼容：从新模块导入并导出
from src.memory_manager import (
    MemoryManager,
    get_memory_manager,
)

__all__ = ["MemoryManager", "get_memory_manager"]