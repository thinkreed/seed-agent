"""
凭证保险库类型定义

包含凭证类型、作用域、访问日志、轮换记录和凭证记录等数据结构。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import logging

logger = logging.getLogger(__name__)


def _get_default_vault_path() -> Path:
    """获取默认保险库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().vault_dir
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "vault"


class CredentialType(StrEnum):
    """凭证类型"""

    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"  # 凭证类型名称，非实际密码
    SSH_KEY = "ssh_key"
    DATABASE_PASSWORD = "database_password"  # 凭证类型名称，非实际密码
    CLOUD_CREDENTIALS = "cloud_credentials"


class CredentialScope(StrEnum):
    """凭证作用域"""

    API_CALL = "api_call"  # 仅允许 API 调用
    FILE_UPLOAD = "file_upload"  # 允许文件上传
    ADMIN = "admin"  # 允许管理操作
    READONLY = "readonly"  # 只读访问


@dataclass
class CredentialAccessLog:
    """凭证访问日志"""

    timestamp: float
    credential_id: str
    scope: str
    requester_id: str | None
    action: str
    success: bool = True
    error: str | None = None


@dataclass
class CredentialRotationRecord:
    """凭证轮换记录"""

    old_value_encrypted: str
    rotated_at: float
    rotated_by: str
    reason: str | None = None


@dataclass
class CredentialRecord:
    """凭证记录"""

    provider: str
    type: str
    value_encrypted: str
    scopes: list[str]
    metadata: dict[str, Any]
    created_at: float
    last_accessed: float | None
    access_count: int
    rotation_history: list[dict[str, Any]] = field(default_factory=list)
    rotated_at: float | None = None
    expiry: float | None = None