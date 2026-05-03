"""
CredentialProxy 单元测试

覆盖:
- 代理执行外部请求
- 临时客户端创建
- 凭证销毁机制
- 请求审计日志
- 并发控制
"""

import os
import sys
import pytest
import tempfile
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.security.credential_vault import CredentialVault, CredentialScope
from src.security.credential_proxy import CredentialProxy, TemporaryClient


# === CredentialProxy 测试 ===

class TestCredentialProxy:
    """测试 CredentialProxy"""

    def setup_method(self):
        """每个测试方法前创建临时 Vault 和 Proxy"""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_path = Path(self.temp_dir) / "vault"

        self.vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        # 存储测试凭证
        self.vault.store_credential(
            provider="openai",
            credential_type="api_key",
            credential_value="sk-test-proxy-123",
            scopes=["api_call"]
        )

        self.proxy = CredentialProxy(
            vault=self.vault,
            max_concurrent_requests=5,
            request_timeout=10.0
        )

    def teardown_method(self):
        """每个测试方法后清理"""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_init_basic(self):
        """基本初始化"""
        assert self.proxy._vault == self.vault
        assert self.proxy._max_concurrent_requests == 5
        assert self.proxy._request_timeout == 10.0
        assert self.proxy._request_semaphore is not None

    def test_init_default_values(self):
        """默认值初始化"""
        proxy = CredentialProxy(self.vault)
        assert proxy._max_concurrent_requests == 10
        assert proxy._request_timeout == 60.0

    def test_supported_providers(self):
        """支持的 Provider 列表"""
        providers = self.proxy.get_supported_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "bailian" in providers

    def test_register_provider(self):
        """注册新 Provider"""
        self.proxy.register_provider(
            provider="custom_llm",
            base_url="https://api.custom.llm/v1",
            client_class="AsyncOpenAI"
        )

        providers = self.proxy.get_supported_providers()
        assert "custom_llm" in providers

    # === 异步请求测试 ===

    @pytest.mark.asyncio
    async def test_execute_external_request_success(self):
        """成功执行外部请求"""
        # 模拟请求函数
        async def mock_request(client, context):
            return {"result": "success", "model": context["model"]}

        result = await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=mock_request,
            request_context={"model": "gpt-4"},
            requester_id="test_user"
        )

        assert result["status"] == "success"
        assert result["result"]["result"] == "success"

    @pytest.mark.asyncio
    async def test_execute_external_request_audit_log(self):
        """请求审计日志"""
        async def mock_request(client, context):
            return {"result": "ok"}

        await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=mock_request,
            request_context={"test": True},
            requester_id="audit_test"
        )

        logs = self.proxy.get_request_audit_log()
        assert len(logs) >= 1

        latest_log = logs[-1]
        assert latest_log["provider"] == "openai"
        assert latest_log["requester_id"] == "audit_test"
        assert latest_log["status"] == "success"

    @pytest.mark.asyncio
    async def test_execute_external_request_timeout(self):
        """请求超时"""
        async def slow_request(client, context):
            await asyncio.sleep(5.0)  # 模拟慢请求
            return {"result": "slow"}

        result = await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=slow_request,
            request_context={},
            timeout=1.0  # 1秒超时
        )

        assert result["status"] == "timeout"
        assert "timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_external_request_credential_not_found(self):
        """凭证不存在"""
        async def mock_request(client, context):
            return {"result": "ok"}

        with pytest.raises(ValueError, match="not found"):
            await self.proxy.execute_external_request(
                provider="unknown_provider",
                credential_type="api_key",
                request_func=mock_request,
                request_context={}
            )

    @pytest.mark.asyncio
    async def test_execute_external_request_scope_denied(self):
        """作用域不允许"""
        # 存储只有 api_call 权限的凭证
        self.vault.store_credential(
            provider="restricted",
            credential_type="api_key",
            credential_value="restricted123",
            scopes=["api_call"]
        )

        async def mock_request(client, context):
            return {"result": "ok"}

        with pytest.raises(PermissionError, match="not allowed"):
            await self.proxy.execute_external_request(
                provider="restricted",
                credential_type="api_key",
                request_func=mock_request,
                request_context={},
                scope="admin"  # 不允许的作用域
            )

    @pytest.mark.asyncio
    async def test_execute_external_request_failure(self):
        """请求失败"""
        async def failing_request(client, context):
            raise Exception("API Error")

        result = await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=failing_request,
            request_context={}
        )

        assert result["status"] == "failed"
        assert "API Error" in result["error"]

    # === 临时客户端测试 ===

    @pytest.mark.asyncio
    async def test_temp_client_created_and_destroyed(self):
        """临时客户端创建和销毁"""
        async def mock_request(client, context):
            # 检查客户端是否有效
            assert client is not None
            return {"result": "ok"}

        await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=mock_request,
            request_context={}
        )

        # 验证临时客户端已销毁
        assert len(self.proxy._active_clients) == 0

    @pytest.mark.asyncio
    async def test_temp_client_credentials_not_exposed(self):
        """凭证不暴露给请求上下文"""
        captured_context = None

        async def capturing_request(client, context):
            captured_context = context
            return {"result": "ok"}

        await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=capturing_request,
            request_context={"model": "gpt-4"}
        )

        # 请求上下文不应该包含凭证
        # （客户端内部有凭证，但不暴露给 context）
        assert "api_key" not in str(captured_context)
        assert "sk-test" not in str(captured_context)

    # === 请求统计测试 ===

    @pytest.mark.asyncio
    async def test_request_stats(self):
        """请求统计"""
        async def mock_request(client, context):
            return {"result": "ok"}

        # 执行多个请求
        for i in range(3):
            await self.proxy.execute_external_request(
                provider="openai",
                credential_type="api_key",
                request_func=mock_request,
                request_context={"index": i}
            )

        stats = self.proxy.get_request_stats()

        assert stats["total_requests"] >= 3
        assert stats["successful"] >= 3
        assert stats["success_rate"] >= 95.0

    # === 并发控制测试 ===

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """并发请求"""
        async def mock_request(client, context):
            await asyncio.sleep(0.1)
            return {"result": context["id"]}

        # 并发执行 5 个请求
        tasks = [
            self.proxy.execute_external_request(
                provider="openai",
                credential_type="api_key",
                request_func=mock_request,
                request_context={"id": i}
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert result["status"] == "success"

    # === 输出过滤测试 ===

    def test_sanitize_request_context(self):
        """过滤请求上下文中的敏感信息"""
        context = {
            "model": "gpt-4",
            "api_key": "sk-secret123",
            "apiKey": "sk-secret456",
            "messages": [{"role": "user", "content": "Hello"}]
        }

        safe_context = self.proxy._sanitize_request_context(context)

        assert safe_context["model"] == "gpt-4"
        assert safe_context["api_key"] == "[REDACTED]"
        assert safe_context["apiKey"] == "[REDACTED]"
        assert safe_context["messages"][0]["content"] == "Hello"

    def test_sanitize_request_context_nested(self):
        """过滤嵌套上下文中的敏感信息"""
        context = {
            "config": {
                "api_key": "nested-secret",
                "model": "gpt-4"
            }
        }

        safe_context = self.proxy._sanitize_request_context(context)

        assert safe_context["config"]["api_key"] == "[REDACTED]"
        assert safe_context["config"]["model"] == "gpt-4"

    # === 清理测试 ===

    def test_clear_request_logs(self):
        """清空请求日志"""
        self.proxy._request_logs.append(
            MagicMock(spec=["timestamp", "provider", "status"])
        )

        self.proxy.clear_request_logs()

        assert len(self.proxy._request_logs) == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired_clients(self):
        """清理过期客户端"""
        # 创建一个过期客户端
        expired_client = TemporaryClient(
            provider="expired",
            client=MagicMock(),
            credential="expired123",
            created_at=time.time() - 400  # 400秒前（超时）
        )
        self.proxy._active_clients["expired"] = expired_client

        count = self.proxy.cleanup_active_clients()

        assert count == 1
        assert "expired" not in self.proxy._active_clients


# === TemporaryClient 测试 ===

class TestTemporaryClient:
    """测试 TemporaryClient"""

    def test_init(self):
        """初始化"""
        mock_client = MagicMock()
        temp_client = TemporaryClient(
            provider="test",
            client=mock_client,
            credential="test123",
            created_at=time.time()
        )

        assert temp_client.provider == "test"
        assert temp_client.client == mock_client
        assert temp_client.credential == "test123"
        assert not temp_client.destroyed

    def test_destroy(self):
        """销毁"""
        mock_client = MagicMock()
        temp_client = TemporaryClient(
            provider="test",
            client=mock_client,
            credential="test123",
            created_at=time.time()
        )

        temp_client.destroy()

        assert temp_client.destroyed
        assert temp_client.client is None
        assert temp_client.credential == ""


# === 集成测试 ===

class TestCredentialProxyIntegration:
    """CredentialProxy 集成测试"""

    def setup_method(self):
        """每个测试方法前创建临时 Vault 和 Proxy"""
        self.temp_dir = tempfile.mkdtemp()
        self.vault_path = Path(self.temp_dir) / "vault"

        self.vault = CredentialVault(
            vault_path=self.vault_path,
            auto_generate_key=True
        )

        self.proxy = CredentialProxy(
            vault=self.vault,
            max_concurrent_requests=5
        )

    def teardown_method(self):
        """每个测试方法后清理"""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    @pytest.mark.asyncio
    async def test_full_request_cycle(self):
        """完整请求周期"""
        # 1. 存储凭证
        self.vault.store_credential(
            provider="openai",
            credential_type="api_key",
            credential_value="sk-full-cycle-123",
            scopes=["api_call"]
        )

        # 2. 执行请求
        async def request_func(client, context):
            return {"data": context["query"]}

        result = await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=request_func,
            request_context={"query": "test query"},
            requester_id="integration_test"
        )

        assert result["status"] == "success"
        assert result["result"]["data"] == "test query"

        # 3. 检查 Vault 审计
        vault_logs = self.vault.get_access_audit_log()
        assert len(vault_logs) >= 1

        # 4. 检查 Proxy 审计
        proxy_logs = self.proxy.get_request_audit_log()
        assert len(proxy_logs) >= 1

        # 5. 验证统计
        vault_stats = self.vault.get_vault_stats()
        assert vault_stats["credentials_count"] >= 1

        proxy_stats = self.proxy.get_request_stats()
        assert proxy_stats["total_requests"] >= 1

    @pytest.mark.asyncio
    async def test_credential_rotation_and_request(self):
        """凭证轮换后请求"""
        # 存储初始凭证
        self.vault.store_credential(
            provider="openai",
            credential_type="api_key",
            credential_value="initial-key",
            scopes=["api_call"]
        )

        # 执行请求（使用初始凭证）
        async def request_func(client, context):
            return {"version": 1}

        result1 = await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=request_func,
            request_context={}
        )
        assert result1["status"] == "success"

        # 轮换凭证
        self.vault.rotate_credential(
            provider="openai",
            credential_type="api_key",
            new_value="rotated-key"
        )

        # 执行请求（使用新凭证）
        result2 = await self.proxy.execute_external_request(
            provider="openai",
            credential_type="api_key",
            request_func=request_func,
            request_context={}
        )
        assert result2["status"] == "success"

        # 验证轮换历史
        stats = self.vault.get_credential_usage_stats("openai", "api_key")
        assert stats["rotation_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])