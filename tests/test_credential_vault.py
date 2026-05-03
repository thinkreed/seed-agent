"""
CredentialVault 单元测试

覆盖:
- 凭证加密存储
- 作用域检查
- 凭证轮换
- 审计日志
- 持久化存储
"""

import os
import sys
import pytest
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.security.credential_vault import (
    CredentialVault,
    CredentialType,
    CredentialScope,
    CredentialRecord,
    CredentialAccessLog,
)


# === CredentialVault 测试 ===

class TestCredentialVault:
    """测试 CredentialVault"""

    def setup_method(self):
        """每个测试方法前创建临时 Vault"""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_path = Path(self.temp_dir) / "vault"

    def teardown_method(self):
        """每个测试方法后清理"""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_init_default_path(self):
        """默认路径初始化"""
        vault = CredentialVault(auto_generate_key=False)
        assert vault._vault_path.exists() or str(vault._vault_path) == str(Path.home() / ".seed" / "vault")

    def test_init_custom_path(self):
        """自定义路径初始化"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )
        assert vault._vault_path == self.vault_path
        assert vault._vault_path.exists()

    def test_init_encryption_key_generation(self):
        """自动生成加密密钥"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )
        assert vault._encryption_key is not None
        assert len(vault._encryption_key) > 0

    def test_init_encryption_key_provided(self):
        """提供加密密钥"""
        import base64
        import secrets
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

        vault = CredentialVault(
            vault_path=self.vault_path,
            encryption_key=key,
            auto_generate_key=False
        )
        assert vault._encryption_key == key

    # === 凭证存储测试 ===

    def test_store_credential_basic(self):
        """基本凭证存储"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        cred_id = vault.store_credential(
            provider="openai",
            credential_type="api_key",
            credential_value="sk-test123"
        )

        assert cred_id == "openai_api_key"
        assert vault.has_credential("openai", "api_key")

    def test_store_credential_with_scopes(self):
        """带作用域的凭证存储"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        cred_id = vault.store_credential(
            provider="aws",
            credential_type="api_key",
            credential_value="AKIAIOSFODNN7EXAMPLE",
            scopes=["api_call", "file_upload"]
        )

        assert cred_id == "aws_api_key"

        # 检查作用域
        creds = vault.list_credentials()
        aws_cred = next((c for c in creds if c["provider"] == "aws"), None)
        assert aws_cred is not None
        assert "api_call" in aws_cred["scopes"]
        assert "file_upload" in aws_cred["scopes"]

    def test_store_credential_with_metadata(self):
        """带元数据的凭证存储"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential(
            provider="github",
            credential_type="api_key",
            credential_value="ghp_test123",
            metadata={"owner": "test_user", "description": "GitHub PAT"}
        )

        creds = vault.list_credentials()
        github_cred = next((c for c in creds if c["provider"] == "github"), None)
        assert github_cred is not None
        assert github_cred["metadata"]["owner"] == "test_user"

    def test_store_credential_empty_value_raises(self):
        """空凭证值抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            vault.store_credential("test", "api_key", "")

    # === 凭证获取测试 ===

    def test_get_credential_basic(self):
        """基本凭证获取"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential(
            provider="openai",
            credential_type="api_key",
            credential_value="sk-test123"
        )

        cred = vault.get_credential(
            provider="openai",
            credential_type="api_key",
            scope="api_call"
        )

        assert cred == "sk-test123"

    def test_get_credential_not_found_raises(self):
        """凭证不存在抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        with pytest.raises(ValueError, match="not found"):
            vault.get_credential("unknown", "api_key", scope="api_call")

    def test_get_credential_scope_denied_raises(self):
        """作用域不允许抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential(
            provider="test",
            credential_type="api_key",
            credential_value="test123",
            scopes=["api_call"]  # 只有 api_call 权限
        )

        with pytest.raises(PermissionError, match="not allowed"):
            vault.get_credential("test", "api_key", scope="admin")

    def test_get_credential_updates_access_stats(self):
        """获取凭证更新访问统计"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "test123")

        # 获取凭证多次
        vault.get_credential("test", "api_key", scope="api_call")
        vault.get_credential("test", "api_key", scope="api_call")

        stats = vault.get_credential_usage_stats("test", "api_key")
        assert stats["total_access_count"] == 2
        assert stats["last_accessed"] is not None

    def test_get_credential_expiry(self):
        """过期凭证抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        # 设置已过期的凭证
        vault.store_credential(
            provider="expired",
            credential_type="api_key",
            credential_value="expired123",
            expiry=time.time() - 100  # 100秒前过期
        )

        with pytest.raises(RuntimeError, match="expired"):
            vault.get_credential("expired", "api_key", scope="api_call")

    # === 凭证轮换测试 ===

    def test_rotate_credential_basic(self):
        """基本凭证轮换"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("openai", "api_key", "sk-old123")

        vault.rotate_credential("openai", "api_key", "sk-new456")

        # 验证新凭证
        cred = vault.get_credential("openai", "api_key", scope="api_call")
        assert cred == "sk-new456"

    def test_rotate_credential_history(self):
        """轮换历史记录"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "old1")
        vault.rotate_credential("test", "api_key", "new1")
        vault.rotate_credential("test", "api_key", "new2")

        stats = vault.get_credential_usage_stats("test", "api_key")
        assert stats["rotation_count"] == 2

    def test_rotate_credential_not_found_raises(self):
        """轮换不存在凭证抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        with pytest.raises(ValueError, match="not found"):
            vault.rotate_credential("unknown", "api_key", "new123")

    def test_rotate_credential_empty_value_raises(self):
        """轮换空值抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "test123")

        with pytest.raises(ValueError, match="cannot be empty"):
            vault.rotate_credential("test", "api_key", "")

    # === 凭证删除测试 ===

    def test_delete_credential_basic(self):
        """基本凭证删除"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "test123")
        assert vault.has_credential("test", "api_key")

        vault.delete_credential("test", "api_key")
        assert not vault.has_credential("test", "api_key")

    def test_delete_credential_not_found_raises(self):
        """删除不存在凭证抛出异常"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        with pytest.raises(ValueError, match="not found"):
            vault.delete_credential("unknown", "api_key")

    # === 审计日志测试 ===

    def test_access_audit_log(self):
        """访问审计日志"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "test123")
        vault.get_credential("test", "api_key", scope="api_call", requester_id="user1")

        logs = vault.get_access_audit_log()
        assert len(logs) >= 2

        # 检查日志内容
        get_log = next((l for l in logs if l["action"] == "get_credential"), None)
        assert get_log is not None
        assert get_log["credential_id"] == "test_api_key"
        assert get_log["requester_id"] == "user1"

    def test_access_audit_log_scope_denied(self):
        """作用域拒绝审计日志"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "test123", scopes=["api_call"])

        try:
            vault.get_credential("test", "api_key", scope="admin")
        except PermissionError:
            pass

        logs = vault.get_access_audit_log()
        failed_log = next((l for l in logs if not l["success"]), None)
        assert failed_log is not None
        assert "not allowed" in failed_log["error"]

    # === 加密/解密测试 ===

    def test_encrypt_decrypt_roundtrip(self):
        """加密解密往返"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        original = "sk-test-secret-key-1234567890"
        encrypted = vault._encrypt(original)
        decrypted = vault._decrypt(encrypted)

        assert decrypted == original
        assert encrypted != original  # 加密后应该不同

    def test_encrypt_different_values_different_outputs(self):
        """不同值加密结果不同"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        enc1 = vault._encrypt("value1")
        enc2 = vault._encrypt("value2")

        assert enc1 != enc2

    # === 持久化测试 ===

    def test_persist_and_load_credentials(self):
        """凭证持久化和加载"""
        vault1 = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault1.store_credential("openai", "api_key", "sk-test123")
        vault1.store_credential("anthropic", "api_key", "sk-ant456")

        # 创建新 Vault 加载持久化数据
        vault2 = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=False
        )
        vault2._encryption_key = vault1._encryption_key
        vault2._load_credentials()

        assert vault2.has_credential("openai", "api_key")
        assert vault2.has_credential("anthropic", "api_key")

    # === 列表和统计测试 ===

    def test_list_credentials_no_sensitive_values(self):
        """列出凭证不暴露敏感值"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test", "api_key", "secret-value-123")

        creds = vault.list_credentials()
        test_cred = next((c for c in creds if c["provider"] == "test"), None)

        assert test_cred is not None
        # 检查没有暴露 value_encrypted
        assert "value_encrypted" not in test_cred
        assert "secret" not in str(test_cred)

    def test_vault_stats(self):
        """Vault 统计信息"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        vault.store_credential("test1", "api_key", "value1")
        vault.store_credential("test2", "api_key", "value2")
        vault.get_credential("test1", "api_key", scope="api_call")

        stats = vault.get_vault_stats()

        assert stats["credentials_count"] == 2
        assert stats["total_accesses"] >= 3  # store + get
        assert stats["encryption_enabled"] == True

    # === 清理测试 ===

    def test_clear_expired_credentials(self):
        """清理过期凭证"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        # 存储一个有效凭证和一个过期凭证
        vault.store_credential("valid", "api_key", "value1")
        vault.store_credential("expired", "api_key", "value2", expiry=time.time() - 100)

        count = vault.clear_expired_credentials()

        assert count == 1
        assert vault.has_credential("valid", "api_key")
        assert not vault.has_credential("expired", "api_key")


# === CredentialScope 测试 ===

class TestCredentialScope:
    """测试 CredentialScope"""

    def test_scope_values(self):
        """作用域值"""
        assert CredentialScope.API_CALL.value == "api_call"
        assert CredentialScope.FILE_UPLOAD.value == "file_upload"
        assert CredentialScope.ADMIN.value == "admin"
        assert CredentialScope.READONLY.value == "readonly"


# === CredentialType 测试 ===

class TestCredentialType:
    """测试 CredentialType"""

    def test_type_values(self):
        """凭证类型值"""
        assert CredentialType.API_KEY.value == "api_key"
        assert CredentialType.OAUTH_TOKEN.value == "oauth_token"
        assert CredentialType.SSH_KEY.value == "ssh_key"
        assert CredentialType.DATABASE_PASSWORD.value == "database_password"


# === 集成测试 ===

class TestCredentialVaultIntegration:
    """CredentialVault 集成测试"""

    def setup_method(self):
        """每个测试方法前创建临时 Vault"""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_path = Path(self.temp_dir) / "vault"

    def teardown_method(self):
        """每个测试方法后清理"""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_full_lifecycle(self):
        """完整生命周期测试"""
        vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        # 1. 存储
        cred_id = vault.store_credential(
            provider="openai",
            credential_type="api_key",
            credential_value="sk-initial-key",
            scopes=["api_call", "file_upload"],
            metadata={"owner": "test"}
        )
        assert cred_id == "openai_api_key"

        # 2. 获取
        cred = vault.get_credential("openai", "api_key", scope="api_call")
        assert cred == "sk-initial-key"

        # 3. 轮换
        vault.rotate_credential("openai", "api_key", "sk-new-key")

        # 4. 验证轮换
        cred = vault.get_credential("openai", "api_key", scope="api_call")
        assert cred == "sk-new-key"

        # 5. 更新作用域
        vault.update_scopes("openai", "api_key", ["api_call"])

        # 6. 验证作用域更新
        try:
            vault.get_credential("openai", "api_key", scope="file_upload")
            assert False, "Should raise PermissionError"
        except PermissionError:
            pass

        # 7. 删除
        vault.delete_credential("openai", "api_key")
        assert not vault.has_credential("openai", "api_key")

        # 8. 检查审计日志
        logs = vault.get_access_audit_log()
        assert len(logs) >= 7  # 至少记录了7个操作


if __name__ == "__main__":
    pytest.main([__file__, "-v"])