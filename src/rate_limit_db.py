"""LLM 请求限流状态持久化

重构版本：原大文件已拆分为多个小模块
此文件保留为向后兼容的导入入口

详细文档请参阅 rate_limit_db/__init__.py 和子模块

模块结构:
- rate_limit_db/_state.py: RateLimitState 数据类 (~15 行)
- rate_limit_db/_path.py: 数据库路径获取 (~20 行)
- rate_limit_db/_connection.py: 连接管理 (~100 行)
- rate_limit_db/_operations.py: 状态操作 (~100 行)
- rate_limit_db/_history.py: 历史操作 (~70 行)

总计: 5 个模块，每个均 < 150 行
"""

# 向后兼容：从新模块导入并导出
from src.rate_limit_db import (
    RateLimitSQLite,
    RateLimitState,
    get_db_path,
)

__all__ = ["RateLimitSQLite", "RateLimitState", "get_db_path"]