"""
凭证隔离沙盒 - 类型定义和常量

包含:
- 预编译正则表达式（性能优化）
- 凭证检测模式
- 导入聚合
"""

import re

from src.sandbox import IsolationLevel
from src.security.constants import (
    BLOCKED_ENV_VARS,
    ENV_VAR_BLOCK_PATTERNS,
    OUTPUT_SANITIZE_PATTERNS,
)

# 预编译正则表达式（性能优化）- 用于输出清洗
_RE_SK_KEY = re.compile(OUTPUT_SANITIZE_PATTERNS["sk_key"])
_RE_BEARER = re.compile(OUTPUT_SANITIZE_PATTERNS["bearer"])
_RE_AWS_KEY = re.compile(OUTPUT_SANITIZE_PATTERNS["aws_key"])
_RE_API_KEY_GENERIC = re.compile(OUTPUT_SANITIZE_PATTERNS["api_key_generic"])

# 凭证访问检测模式
CREDENTIAL_ACCESS_PATTERNS = [
    "os.environ",
    "getenv",
    "environ.get",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "BAILIAN_API_KEY",
    "AWS_ACCESS_KEY",
    "GITHUB_TOKEN",
    "api_key",
    "apiKey",
    "API_KEY",
]

# 默认屏蔽的环境变量列表
DEFAULT_BLOCKED_ENV_VARS = BLOCKED_ENV_VARS.copy()

# 环境变量屏蔽模式
DEFAULT_ENV_VAR_BLOCK_PATTERNS = ENV_VAR_BLOCK_PATTERNS.copy()