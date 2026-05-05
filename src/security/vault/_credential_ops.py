"""
凭证保险库凭证操作模块

包含凭证的存储、获取、轮换、删除等操作功能。
"""

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
    from src.security.vault._types import CredentialRecord

logger = logging.getLogger(__name__)


class CredentialOpsMixin:
    """凭证操作功能 Mixin 类

    提供凭证存储、获取、轮换、删除等操作功能。
    需要与 CredentialVault 配合使用，依赖 _credentials, _vault_path, _encrypt, _decrypt, _persist_credentials, _log_access 等方法/属性。
    """

    _credentials: dict[str, "CredentialRecord"]
    _vault_path: "Path"

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
        from src.security.vault._types import CredentialRecord, CredentialScope

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
        scope: str = "api_call",
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
        from src.security.vault._types import CredentialRotationRecord

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
        record.rotation_history.append(
            {
                "old_value_encrypted": rotation_record.old_value_encrypted,
                "rotated_at": rotation_record.rotated_at,
                "rotated_by": rotation_record.rotated_by,
                "reason": rotation_record.reason,
            }
        )

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
            result.append(
                {
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
                }
            )

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

    def clear_expired_credentials(self) -> int:
        """清理过期凭证

        Returns:
            清理的凭证数量
        """
        expired_ids = [
            cred_id
            for cred_id, record in self._credentials.items()
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