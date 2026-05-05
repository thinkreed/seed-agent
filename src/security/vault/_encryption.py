"""
凭证保险库加密模块

包含加密、解密、密钥生成等加密相关功能。
"""

import base64
import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)


class EncryptionMixin:
    """加密功能 Mixin 类

    提供 Fernet 加密、解密、密钥生成等功能。
    需要与 CredentialVault 配合使用，依赖 _vault_path 和 _encryption_key 属性。
    """

    _vault_path: Path
    _encryption_key: str | None

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
                with open(key_path) as f:
                    key = f.read().strip()
                logger.info("Loaded existing vault encryption key")
                return key
            except PermissionError:
                # 权限错误不应被静默处理，这可能表示严重的安全问题
                logger.exception("Permission denied loading vault key")
                raise
            except OSError as e:
                # 其他 I/O 错误（如文件损坏）可以恢复
                logger.warning(
                    f"Failed to load vault key (I/O error): {e}, generating new key"
                )

        # 生成新密钥
        key = self._generate_encryption_key()

        # 存储密钥
        self._vault_path.mkdir(parents=True, exist_ok=True)
        try:
            with open(key_path, "w") as f:
                f.write(key)
        except PermissionError:
            logger.exception("Permission denied writing vault key")
            raise
        except OSError:
            logger.exception("Failed to write vault key")
            raise

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
            random_bytes = secrets.token_bytes(32)
            key_str: str = base64.urlsafe_b64encode(random_bytes).decode()
            logger.warning(
                "cryptography package not available, using fallback key generation. "
                "Install cryptography for proper encryption: pip install cryptography"
            )
            return key_str

    def _encrypt(self, value: str) -> str:
        """加密凭证

        Args:
            value: 原始凭证值

        Returns:
            加密后的字符串（Base64 编码）

        Raises:
            RuntimeError: 加密密钥未设置或 cryptography 包未安装
        """
        if not self._encryption_key:
            raise RuntimeError("Encryption key not set")

        try:
            from cryptography.fernet import Fernet

            fernet = Fernet(self._encryption_key.encode())
            encrypted = fernet.encrypt(value.encode())
            return base64.b64encode(encrypted).decode()
        except ImportError as e:
            # 安全：不再使用 base64 fallback，强制要求 cryptography
            raise RuntimeError(
                "cryptography package is required for credential encryption. "
                "Install with: pip install cryptography. "
                "Base64 encoding is NOT encryption and must not be used for credentials."
            ) from e

    def _decrypt(self, encrypted_value: str) -> str:
        """解密凭证

        Args:
            encrypted_value: 加密的凭证值

        Returns:
            原始凭证值

        Raises:
            RuntimeError: 加密密钥未设置或 cryptography 包未安装
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
        except ImportError as e:
            # 安全：不再使用 base64 fallback，强制要求 cryptography
            raise RuntimeError(
                "cryptography package is required for credential decryption. "
                "Install with: pip install cryptography"
            ) from e
        except Exception as e:
            logger.exception(f"Failed to decrypt credential: {e}")
            raise ValueError(f"Decryption failed: {type(e).__name__}") from e