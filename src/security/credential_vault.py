"""
凭证保险库 - CredentialVault

基于 Harness Engineering "凭证永不进沙盒" 设计理念：
- 所有凭证存储在独立的加密保险库中
- Harness 和 Sandbox 无法直接访问
- 支持凭证轮换
- 支持审计日志
- 按作用域获取凭证（最小权限原则）

核心特性:
- Fernet 加密存储
- 作用域权限检查
- 凭证轮换历史
- 访问审计日志
- 持久化存储

参考来源: Harness Engineering "凭证永不进沙盒"
"""

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认保险库路径
DEFAULT_VAULT_PATH = Path(os.path.expanduser("~")) / ".seed" / "vault"


class CredentialType(str, Enum):
    """凭证类型"""
    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"
    SSH_KEY = "ssh_key"
    DATABASE_PASSWORD = "database_password"
    CLOUD_CREDENTIALS = "cloud_credentials"


class CredentialScope(str, Enum):
    """凭证作用域"""
    API_CALL = "api_call"          # 仅允许 API 调用
    FILE_UPLOAD = "file_upload"    # 允许文件上传
    ADMIN = "admin"                # 允许管理操作
    READONLY = "readonly"          # 只读访问


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


class CredentialVault:
    """凭证保险库

    所有凭证存储在独立的加密存储中，Harness 和 Sandbox 无法直接访问。

    核心职责:
    1. 凭证加密存储 (Fernet)
    2. 作用域检查 (最小权限原则)
    3. 凭证轮换 (历史记录)
    4. 访问审计 (所有访问可追溯)
    5. 持久化存储 (JSON + 文件权限)

    安全特性:
    - 加密存储：所有凭证使用 Fernet 对称加密
    - 作用域限制：按请求作用域获取凭证
    - 访问审计：记录所有凭证访问
    - 轮换支持：支持凭证轮换并记录历史

    Example:
        vault = CredentialVault()

        # 存储凭证
        vault.store_credential("openai", "api_key", "sk-test123", scopes=["api_call"])

        # 获取凭证（按作用域）
        credential = vault.get_credential("openai", "api_key", scope="api_call")

        # 轮换凭证
        vault.rotate_credential("openai", "api_key", "sk-new456")

        # 查看审计日志
        audit_log = vault.get_access_audit_log()
    """

    # 凭证类型描述
    CREDENTIAL_TYPES = {
        CredentialType.API_KEY: "API 密钥",
        CredentialType.OAUTH_TOKEN: "OAuth 令牌",
        CredentialType.SSH_KEY: "SSH 密钥",
        CredentialType.DATABASE_PASSWORD: "数据库密码",
        CredentialType.CLOUD_CREDENTIALS: "云服务凭证",
    }

    # 作用域权限描述
    SCOPE_PERMISSIONS = {
        CredentialScope.API_CALL: "仅允许 API 调用",
        CredentialScope.FILE_UPLOAD: "允许文件上传",
        CredentialScope.ADMIN: "允许管理操作",
        CredentialScope.READONLY: "只读访问",
    }

    def __init__(
        self,
        vault_path: Path | None = None,
        encryption_key: str | None = None,
        auto_generate_key: bool = True,
    ):
        """初始化凭证保险库

        Args:
            vault_path: 保险库存储路径，默认 ~/.seed/vault
            encryption_key: 加密密钥（可选，自动生成）
            auto_generate_key: 是否自动生成加密密钥
        """
        self._vault_path = vault_path or DEFAULT_VAULT_PATH
        self._credentials: dict[str, CredentialRecord] = {}
        self._access_logs: list[CredentialAccessLog] = []
        self._max_access_logs = 10000

        # 初始化加密密钥
        self._encryption_key: str | None = None
        if encryption_key:
            self._encryption_key = encryption_key
        elif auto_generate_key:
            self._encryption_key = self._init_encryption_key()

        # 初始化保险库
        self._init_vault()

        logger.info(
            f"CredentialVault initialized: "
            f"path={self._vault_path}, "
            f"credentials={len(self._credentials)}, "
            f"encryption_key_set={self._encryption_key is not None}"
        )

    def _init_encryption_key(self) -> str:
        """初始化加密密钥

        尝试加载已有密钥，不存在则生成新密钥

        Returns:
            加密密钥字符串
        """
        key_path = self._vault_path / ".vault_key"

        # 尝试加载已有密钥
        if key_path.exists():
            try:
                with open(key_path, "r") as f:
                    key = f.read().strip()
                logger.info("Loaded existing vault encryption key")
                return key
            except Exception as e:
                logger.warning(f"Failed to load vault key: {e}, generating new key")

        # 生成新密钥
        key = self._generate_encryption_key()

        # 存储密钥
        self._vault_path.mkdir(parents=True, exist_ok=True)
        with open(key_path, "w") as f:
            f.write(key)

        # 设置文件权限（仅 owner 可读写）
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            logger.warning(f"Failed to set permissions on {key_path}")

        logger.info(f"Generated new vault encryption key: {key_path}")
        return key

    def _generate_encryption_key(self) -> str:
        """生成加密密钥

        使用 cryptography.fernet 生成安全密钥

        Returns:
            Fernet 密钥字符串
        """
        try:
            from cryptography.fernet import Fernet
            key_bytes: bytes = Fernet.generate_key()
            return key_bytes.decode()
        except ImportError:
            # 如果 cryptography 不可用，使用 base64 编码的随机字节
            import secrets
            random_bytes = secrets.token_bytes(32)
            key_str: str = base64.urlsafe_b64encode(random_bytes).decode()
            logger.warning(
                "cryptography package not available, using fallback key generation. "
                "Install cryptography for proper encryption: pip install cryptography"
            )
            return key_str

    def _init_vault(self) -> None:
        """初始化保险库

        创建目录结构，加载已有凭证和审计日志
        """
        # 创建保险库目录
        self._vault_path.mkdir(parents=True, exist_ok=True)

        # 加载已有凭证
        self._load_credentials()

        # 加载审计日志
        self._load_access_logs()

        logger.debug(f"Vault initialized with {len(self._credentials)} credentials")

    # === 凭证管理 ===

    def store_credential(
        self,
        provider: str,
        credential_type: str,
        credential_value: str,
        scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        expiry: float | None = None,
    ) -> str:
        """存储凭证

        Args:
            provider: 提供商名称 (如 "openai", "aws", "github")
            credential_type: 凭证类型 (如 "api_key")
            credential_value: 凭证值
            scopes: 允许的作用域列表，默认 ["api_call"]
            metadata: 元数据 (如 description, owner)
            expiry: 过期时间（Unix timestamp，可选）

        Returns:
            credential_id: 凭证唯一标识

        Raises:
            ValueError: 凭证值无效
        """
        if not credential_value:
            raise ValueError("Credential value cannot be empty")

        credential_id = f"{provider}_{credential_type}"

        # 加密存储
        encrypted_value = self._encrypt(credential_value)

        # 创建凭证记录
        record = CredentialRecord(
            provider=provider,
            type=credential_type,
            value_encrypted=encrypted_value,
            scopes=scopes or [CredentialScope.API_CALL.value],
            metadata=metadata or {},
            created_at=time.time(),
            last_accessed=None,
            access_count=0,
            rotation_history=[],
            expiry=expiry,
        )

        self._credentials[credential_id] = record

        # 持久化
        self._persist_credentials()

        # 记录存储操作
        self._log_access(
            credential_id=credential_id,
            scope="store",
            requester_id=None,
            action="store_credential",
            success=True,
        )

        logger.info(f"Credential stored: {credential_id}, scopes={record.scopes}")
        return credential_id

    def get_credential(
        self,
        provider: str,
        credential_type: str,
        scope: str = CredentialScope.API_CALL.value,
        requester_id: str | None = None,
    ) -> str:
        """获取凭证

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            scope: 请求的作用域（最小权限原则）
            requester_id: 请求者 ID (用于审计)

        Returns:
            凭证值（临时解密）

        Raises:
            ValueError: 凭证不存在
            PermissionError: 作用域不允许
            RuntimeError: 凭证已过期
        """
        credential_id = f"{provider}_{credential_type}"

        # 检查凭证是否存在
        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        record = self._credentials[credential_id]

        # 1. 过期检查
        if record.expiry and time.time() > record.expiry:
            self._log_access(
                credential_id=credential_id,
                scope=scope,
                requester_id=requester_id,
                action="get_credential",
                success=False,
                error="Credential expired",
            )
            raise RuntimeError(f"Credential expired: {credential_id}")

        # 2. 作用域检查（最小权限原则）
        if scope not in record.scopes:
            self._log_access(
                credential_id=credential_id,
                scope=scope,
                requester_id=requester_id,
                action="get_credential",
                success=False,
                error=f"Scope '{scope}' not allowed. Allowed: {record.scopes}",
            )
            raise PermissionError(
                f"Scope '{scope}' not allowed for {credential_id}. "
                f"Allowed scopes: {record.scopes}"
            )

        # 3. 解密凭证（临时）
        decrypted_value = self._decrypt(record.value_encrypted)

        # 4. 更新访问统计
        record.last_accessed = time.time()
        record.access_count += 1

        # 5. 记录访问日志
        self._log_access(
            credential_id=credential_id,
            scope=scope,
            requester_id=requester_id,
            action="get_credential",
            success=True,
        )

        logger.debug(
            f"Credential accessed: {credential_id}, "
            f"scope={scope}, requester={requester_id}"
        )

        return decrypted_value

    def rotate_credential(
        self,
        provider: str,
        credential_type: str,
        new_value: str,
        rotated_by: str = "system",
        reason: str | None = None,
    ) -> None:
        """轮换凭证

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            new_value: 新凭证值
            rotated_by: 轮换执行者
            reason: 轮换原因

        Raises:
            ValueError: 凭证不存在或新值无效
        """
        if not new_value:
            raise ValueError("New credential value cannot be empty")

        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        record = self._credentials[credential_id]

        # 记录轮换历史
        rotation_record = CredentialRotationRecord(
            old_value_encrypted=record.value_encrypted,
            rotated_at=time.time(),
            rotated_by=rotated_by,
            reason=reason,
        )
        record.rotation_history.append({
            "old_value_encrypted": rotation_record.old_value_encrypted,
            "rotated_at": rotation_record.rotated_at,
            "rotated_by": rotation_record.rotated_by,
            "reason": rotation_record.reason,
        })

        # 加密新值
        encrypted_value = self._encrypt(new_value)

        # 更新凭证
        record.value_encrypted = encrypted_value
        record.rotated_at = time.time()

        # 持久化
        self._persist_credentials()

        # 记录轮换操作
        self._log_access(
            credential_id=credential_id,
            scope="rotate",
            requester_id=rotated_by,
            action="rotate_credential",
            success=True,
        )

        logger.info(
            f"Credential rotated: {credential_id}, "
            f"rotated_by={rotated_by}, reason={reason}"
        )

    def delete_credential(
        self,
        provider: str,
        credential_type: str,
        requester_id: str | None = None,
    ) -> bool:
        """删除凭证

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            requester_id: 请求者 ID

        Returns:
            是否成功删除

        Raises:
            ValueError: 凭证不存在
        """
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        # 删除凭证
        del self._credentials[credential_id]

        # 持久化
        self._persist_credentials()

        # 记录删除操作
        self._log_access(
            credential_id=credential_id,
            scope="delete",
            requester_id=requester_id,
            action="delete_credential",
            success=True,
        )

        logger.info(f"Credential deleted: {credential_id}, requester={requester_id}")
        return True

    def list_credentials(self) -> list[dict[str, Any]]:
        """列出所有凭证（不暴露凭证值）

        Returns:
            凭证列表（不含敏感值）
        """
        result: list[dict[str, Any]] = []

        for cred_id, record in self._credentials.items():
            result.append({
                "credential_id": cred_id,
                "provider": record.provider,
                "type": record.type,
                "scopes": record.scopes,
                "created_at": record.created_at,
                "last_accessed": record.last_accessed,
                "access_count": record.access_count,
                "rotation_count": len(record.rotation_history),
                "last_rotated_at": record.rotated_at,
                "expiry": record.expiry,
                "metadata": record.metadata,
            })

        return result

    def has_credential(self, provider: str, credential_type: str) -> bool:
        """检查凭证是否存在"""
        credential_id = f"{provider}_{credential_type}"
        return credential_id in self._credentials

    def update_scopes(
        self,
        provider: str,
        credential_type: str,
        scopes: list[str],
        requester_id: str | None = None,
    ) -> None:
        """更新凭证作用域

        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            scopes: 新作用域列表
            requester_id: 请求者 ID

        Raises:
            ValueError: 凭证不存在
        """
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")

        self._credentials[credential_id].scopes = scopes

        # 持久化
        self._persist_credentials()

        # 记录更新操作
        self._log_access(
            credential_id=credential_id,
            scope="update",
            requester_id=requester_id,
            action="update_scopes",
            success=True,
        )

        logger.info(f"Credential scopes updated: {credential_id}, scopes={scopes}")

    # === 加密/解密 ===

    def _encrypt(self, value: str) -> str:
        """加密凭证

        Args:
            value: 原始凭证值

        Returns:
            加密后的字符串（Base64 编码）

        Raises:
            RuntimeError: 加密密钥未设置
        """
        if not self._encryption_key:
            raise RuntimeError("Encryption key not set")

        try:
            from cryptography.fernet import Fernet

            fernet = Fernet(self._encryption_key.encode())
            encrypted = fernet.encrypt(value.encode())
            return base64.b64encode(encrypted).decode()
        except ImportError:
            # Fallback: 使用简单的 base64 编码（不安全，仅用于测试）
            logger.warning(
                "cryptography not available, using base64 fallback (NOT SECURE)"
            )
            return base64.b64encode(value.encode()).decode()

    def _decrypt(self, encrypted_value: str) -> str:
        """解密凭证

        Args:
            encrypted_value: 加密的凭证值

        Returns:
            原始凭证值

        Raises:
            RuntimeError: 加密密钥未设置
            ValueError: 解密失败
        """
        if not self._encryption_key:
            raise RuntimeError("Encryption key not set")

        try:
            from cryptography.fernet import Fernet

            fernet = Fernet(self._encryption_key.encode())
            decoded = base64.b64decode(encrypted_value.encode())
            decrypted = fernet.decrypt(decoded)
            return decrypted.decode()
        except ImportError:
            # Fallback: base64 解码
            logger.warning("cryptography not available, using base64 fallback")
            return base64.b64decode(encrypted_value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt credential: {e}")
            raise ValueError(f"Decryption failed: {type(e).__name__}")

    # === 审计日志 ===

    def _log_access(
        self,
        credential_id: str,
        scope: str,
        requester_id: str | None,
        action: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """记录凭证访问"""
        log_entry = CredentialAccessLog(
            timestamp=time.time(),
            credential_id=credential_id,
            scope=scope,
            requester_id=requester_id,
            action=action,
            success=success,
            error=error,
        )

        self._access_logs.append(log_entry)

        # 限制日志大小
        if len(self._access_logs) > self._max_access_logs:
            self._access_logs = self._access_logs[-self._max_access_logs:]

        # 持久化审计日志
        self._persist_audit_log()

    def get_access_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取访问审计日志

        Args:
            limit: 返回条数限制

        Returns:
            审计日志列表
        """
        logs = self._access_logs[-limit:]
        return [
            {
                "timestamp": log.timestamp,
                "credential_id": log.credential_id,
                "scope": log.scope,
                "requester_id": log.requester_id,
                "action": log.action,
                "success": log.success,
                "error": log.error,
            }
            for log in logs
        ]

    def get_credential_usage_stats(self, provider: str, credential_type: str) -> dict[str, Any]:
        """获取凭证使用统计

        Args:
            provider: 提供商名称
            credential_type: 凭证类型

        Returns:
            使用统计数据
        """
        credential_id = f"{provider}_{credential_type}"

        if credential_id not in self._credentials:
            return {}

        record = self._credentials[credential_id]

        # 过滤相关访问日志
        accesses = [
            log for log in self._access_logs
            if log.credential_id == credential_id
        ]

        return {
            "credential_id": credential_id,
            "provider": record.provider,
            "type": record.type,
            "total_access_count": record.access_count,
            "last_accessed": record.last_accessed,
            "created_at": record.created_at,
            "rotation_count": len(record.rotation_history),
            "last_rotated_at": record.rotated_at,
            "expiry": record.expiry,
            "recent_accesses": [
                {
                    "timestamp": log.timestamp,
                    "scope": log.scope,
                    "requester_id": log.requester_id,
                    "success": log.success,
                }
                for log in accesses[-10:]
            ],
            "success_rate": (
                sum(1 for a in accesses if a.success) / len(accesses) * 100
                if accesses else 100.0
            ),
        }

    def get_vault_stats(self) -> dict[str, Any]:
        """获取保险库统计信息"""
        total_accesses = len(self._access_logs)
        successful = sum(1 for log in self._access_logs if log.success)

        return {
            "vault_path": str(self._vault_path),
            "credentials_count": len(self._credentials),
            "access_logs_count": total_accesses,
            "encryption_enabled": self._encryption_key is not None,
            "total_accesses": total_accesses,
            "successful_accesses": successful,
            "failed_accesses": total_accesses - successful,
            "success_rate": (successful / total_accesses * 100) if total_accesses else 100.0,
        }

    # === 持久化 ===

    def _persist_credentials(self) -> None:
        """持久化凭证到文件"""
        credentials_file = self._vault_path / "credentials.json"

        # 转换为可序列化格式
        data = {
            cred_id: {
                "provider": record.provider,
                "type": record.type,
                "value_encrypted": record.value_encrypted,
                "scopes": record.scopes,
                "metadata": record.metadata,
                "created_at": record.created_at,
                "last_accessed": record.last_accessed,
                "access_count": record.access_count,
                "rotation_history": record.rotation_history,
                "rotated_at": record.rotated_at,
                "expiry": record.expiry,
            }
            for cred_id, record in self._credentials.items()
        }

        with open(credentials_file, "w") as f:
            json.dump(data, f, indent=2)

        # 设置文件权限
        try:
            os.chmod(credentials_file, 0o600)
        except OSError:
            logger.warning(f"Failed to set permissions on {credentials_file}")

        logger.debug(f"Credentials persisted: {len(self._credentials)} records")

    def _load_credentials(self) -> None:
        """从文件加载凭证"""
        credentials_file = self._vault_path / "credentials.json"

        if not credentials_file.exists():
            logger.debug("No existing credentials file")
            return

        try:
            with open(credentials_file, "r") as f:
                data = json.load(f)

            for cred_id, record_data in data.items():
                record = CredentialRecord(
                    provider=record_data["provider"],
                    type=record_data["type"],
                    value_encrypted=record_data["value_encrypted"],
                    scopes=record_data["scopes"],
                    metadata=record_data["metadata"],
                    created_at=record_data["created_at"],
                    last_accessed=record_data.get("last_accessed"),
                    access_count=record_data.get("access_count", 0),
                    rotation_history=record_data.get("rotation_history", []),
                    rotated_at=record_data.get("rotated_at"),
                    expiry=record_data.get("expiry"),
                )
                self._credentials[cred_id] = record

            logger.info(f"Loaded {len(self._credentials)} credentials from vault")
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            # 初始化为空
            self._credentials = {}

    def _persist_audit_log(self) -> None:
        """持久化审计日志（追加模式）"""
        audit_file = self._vault_path / "audit_log.jsonl"

        # 只追加最近的日志条目（避免重复写入）
        recent_logs = self._access_logs[-10:]

        with open(audit_file, "a") as f:
            for log in recent_logs:
                entry = {
                    "timestamp": log.timestamp,
                    "credential_id": log.credential_id,
                    "scope": log.scope,
                    "requester_id": log.requester_id,
                    "action": log.action,
                    "success": log.success,
                    "error": log.error,
                }
                f.write(json.dumps(entry) + "\n")

    def _load_access_logs(self) -> None:
        """从文件加载审计日志"""
        audit_file = self._vault_path / "audit_log.jsonl"

        if not audit_file.exists():
            logger.debug("No existing audit log file")
            return

        try:
            with open(audit_file, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        log_entry = CredentialAccessLog(
                            timestamp=entry["timestamp"],
                            credential_id=entry["credential_id"],
                            scope=entry["scope"],
                            requester_id=entry.get("requester_id"),
                            action=entry["action"],
                            success=entry.get("success", True),
                            error=entry.get("error"),
                        )
                        self._access_logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue

            logger.info(f"Loaded {len(self._access_logs)} audit log entries")
        except Exception as e:
            logger.error(f"Failed to load audit logs: {e}")

    # === 清理 ===

    def clear_expired_credentials(self) -> int:
        """清理过期凭证

        Returns:
            清理的凭证数量
        """
        expired_ids = [
            cred_id for cred_id, record in self._credentials.items()
            if record.expiry and time.time() > record.expiry
        ]

        for cred_id in expired_ids:
            del self._credentials[cred_id]
            self._log_access(
                credential_id=cred_id,
                scope="cleanup",
                requester_id="system",
                action="clear_expired",
                success=True,
            )

        if expired_ids:
            self._persist_credentials()
            logger.info(f"Cleaned up {len(expired_ids)} expired credentials")

        return len(expired_ids)

    def clear_audit_logs(self) -> None:
        """清空审计日志"""
        self._access_logs.clear()

        # 删除日志文件
        audit_file = self._vault_path / "audit_log.jsonl"
        if audit_file.exists():
            try:
                audit_file.unlink()
                logger.info("Audit logs cleared")
            except Exception as e:
                logger.warning(f"Failed to delete audit log file: {e}")