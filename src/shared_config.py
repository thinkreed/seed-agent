"""共享配置模块 - 向后兼容入口

所有功能已迁移至 shared_config 包：
- _path_management.py: 路径管理功能
- _config_dataclasses.py: 配置数据类

此文件仅作为导入入口，保持向后兼容。
"""

# 从包导入所有内容
from src.shared_config import *  # noqa: F401, F403
from src.shared_config import __all__  # noqa: F401