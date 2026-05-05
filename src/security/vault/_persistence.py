"""
凭证保险库持久化模块

包含凭证和审计日志的持久化存储功能。
"""

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.security.vault._types import CredentialAccessLog, CredentialRecord

logger = logging.getLogger(__name__)


class PersistenceMixin:
    """持久化功能 Mixin 类

    提供凭证和审计日志的持久化存储功能。
    需要与 CredentialVault 配合使用，依赖 _vault_path, _credentials, _access_logs 属性。
    """

    _vault_path: Path
    _credentials: dict[str, "CredentialRecord"]
    _access_logs: list["CredentialAccessLog"]

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

        try:
            with open(credentials_file, "w") as f:
                json.dump(data, f, indent=2)
        except PermissionError as e:
            logger.exception(f"Permission denied writing credentials: {e}")
            raise
        except OSError as e:
            logger.exception(f"Failed to persist credentials: {e}")
            raise

        # 设置文件权限
        try:
            os.chmod(credentials_file, 0o600)
        except OSError:
            logger.warning(f"Failed to set permissions on {credentials_file}")

        logger.debug(f"Credentials persisted: {len(self._credentials)} records")

    def _load_credentials(self) -> None:
        """从文件加载凭证"""
        from src.security.vault._types import CredentialRecord

        credentials_file = self._vault_path / "credentials.json"

        if not credentials_file.exists():
            logger.debug("No existing credentials file")
            return

        try:
            with open(credentials_file) as f:
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
            logger.exception(f"Failed to load credentials: {e}")
            # 初始化为空
            self._credentials = {}

    def _persist_audit_log(self) -> None:
        """持久化审计日志（追加模式）"""
        from src.security.vault._types import CredentialAccessLog

        audit_file = self._vault_path / "audit_log.jsonl"

        # 只追加最近的日志条目（避免重复写入）
        recent_logs = self._access_logs[-10:]

        try:
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
        except PermissionError as e:
            logger.exception(f"Permission denied writing audit log: {e}")
            # 审计日志写入失败不应阻断主流程，但需记录
        except OSError as e:
            logger.warning(f"Failed to persist audit log: {e}")

    def _load_access_logs(self) -> None:
        """从文件加载审计日志"""
        from src.security.vault._types import CredentialAccessLog

        audit_file = self._vault_path / "audit_log.jsonl"

        if not audit_file.exists():
            logger.debug("No existing audit log file")
            return

        try:
            with open(audit_file) as f:
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
            logger.exception(f"Failed to load audit logs: {e}")