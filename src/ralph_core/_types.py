"""
Ralph Loop 类型定义

包含完成类型枚举和常量配置。
"""

from enum import Enum

# 默认配置常量
MAX_ITERATIONS = 1000
MAX_DURATION = 8 * 60 * 60  # 8小时
ITERATION_INTERVAL = 5  # 上下文重置间隔


class CompletionType(Enum):
    """完成验证类型"""

    TEST_PASS = "test_pass"  # 测试通过
    FILE_EXISTS = "file_exists"  # 目标文件存在
    MARKER_FILE = "marker_file"  # 完成标志文件
    GIT_CLEAN = "git_clean"  # Git 工作区干净
    CUSTOM_CHECK = "custom_check"  # 自定义验证函数