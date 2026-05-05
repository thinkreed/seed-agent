"""
安全模块常量定义 - Security Constants

统一管理敏感环境变量列表，避免重复定义。

使用:
- CredentialIsolatedSandbox: 环境变量过滤
- SinglePurposeToolFactory: 安全环境构建

参考来源: Harness Engineering "凭证永不进沙盒"
"""

# 需要屏蔽的敏感环境变量列表
# 统一来源：credential_isolated_sandbox.py + single_purpose_tools.py
SENSITIVE_ENV_VARS = [
    # API Keys
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "BAILIAN_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_TOKEN",
    # Cloud Credentials
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    # Database Credentials
    "DATABASE_URL",
    "DB_PASSWORD",
    "MYSQL_PASSWORD",
    "POSTGRES_PASSWORD",
    "MONGODB_PASSWORD",
    # Service Tokens
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "SLACK_TOKEN",
    "DISCORD_TOKEN",
    "TELEGRAM_TOKEN",
    # SSH Keys
    "SSH_PRIVATE_KEY",
    "SSH_AUTH_SOCK",
    # Generic
    "API_KEY",
    "SECRET_KEY",
    "PRIVATE_KEY",
    "PASSWORD",
    "TOKEN",
]

# 环境变量模式匹配后缀（用于动态过滤）
ENV_VAR_BLOCK_PATTERNS = ["_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PRIVATE"]

# 凭证访问检测模式（用于代码检测）
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

# 输出清洗正则表达式模式（预编译为常量字符串）
OUTPUT_SANITIZE_PATTERNS = {
    "sk_key": r"sk-[a-zA-Z0-9]{20,}",  # OpenAI sk-* 模式
    "bearer": r"Bearer\s+[a-zA-Z0-9_-]{20,}",  # Bearer token
    "aws_key": r"AKIA[A-Z0-9]{16}",  # AWS Access Key
    "api_key_generic": r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}',  # 通用 API Key
}

# 默认屏蔽的环境变量列表（用于 CredentialIsolatedSandbox）
BLOCKED_ENV_VARS = SENSITIVE_ENV_VARS.copy()