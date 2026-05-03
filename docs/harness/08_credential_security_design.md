# 优化点 08: 凭证安全架构 (Vault + Proxy)

> **版本**: v1.1
> **创建日期**: 2026-05-03
> **完成日期**: 2026-05-03
> **状态**: ✅ 已完成
> **优先级**: 高
> **依赖**: 02_harness_sandbox_decoupling_design
> **参考来源**: Harness Engineering "凭证永不进沙盒"

---

## 实施总结

### 已实现组件

| 组件 | 文件 | 状态 |
|------|------|------|
| **CredentialVault** | `src/security/credential_vault.py` | ✅ 已实现 |
| **CredentialProxy** | `src/security/credential_proxy.py` | ✅ 已实现 |
| **CredentialIsolatedSandbox** | `src/security/credential_isolated_sandbox.py` | ✅ 已实现 |
| **SecureHarness** | `src/security/secure_harness.py` | ✅ 已实现 |
| **LLMGateway Vault 集成** | `src/client.py` | ✅ 已实现 |
| **测试覆盖** | `tests/test_credential_vault.py`, `tests/test_credential_proxy.py`, `tests/test_security.py` | ✅ 已实现 |

### 核心特性验证

- ✅ 凭证加密存储（Fernet）
- ✅ 作用域检查（最小权限原则）
- ✅ 凭证轮换（历史记录）
- ✅ 访问审计日志
- ✅ 环境变量过滤（Sandbox 凭证隔离）
- ✅ 临时客户端创建与销毁
- ✅ 请求审计日志

---

## 问题分析

### Harness Engineering 凭证安全理念

**核心理念**: **凭证永不进沙盒**

> 所有第三方凭证存储在独立的保险库中，Harness 和 Sandbox 都无法直接访问。当需要调用外部工具时，通过代理从保险库按需获取凭证并执行请求。凭证始终不暴露给沙盒中的代码。

**架构设计**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Vault (保险库)                            │
│                                                              │
│    - 所有第三方凭证存储在独立的保险库                            │
│    - Harness 和 Sandbox 都无法直接访问                        │
│    - 支持凭证轮换                                             │
│    - 支持审计日志                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ 按需获取凭证
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Proxy (代理)                              │
│                                                              │
│    - 需调用外部工具时，通过代理从 Vault 获取凭证                 │
│    - 执行请求后，凭证立即销毁                                  │
│    - 凭证始终不暴露给 Sandbox                                 │
│    - 所有外部调用可审计                                       │
└─────────────────────────────────────────────────────────────┐
                            │
                            │ 路由请求
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox (沙盒)                            │
│                                                              │
│    - 执行环境，凭证永不进入                                    │
│    - 代码执行无法访问 API Key                                 │
│    - 安全隔离                                                 │
└─────────────────────────────────────────────────────────────┘
```

**优势**:
- 遵循最小权限原则
- 所有外部调用可审计
- 凭证可统一轮换
- Sandbox 中代码无法泄露凭证

### seed-agent 当前状态

**API Key 管理方式**:

```python
# config.json
{
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",  // 环境变量引用
      "models": [...]
    }
  }
}

# client.py
def _resolve_api_key(self, api_key: str) -> str:
    """解析 API Key,支持环境变量引用"""
    if api_key.startswith("${") and api_key.endswith("}"):
        env_var = api_key[2:-1]
        return os.environ.get(env_var, "").strip()  // 直接访问环境变量
    return api_key.strip()

# code_as_policy 执行
# Sandbox 内的 Python 代码可以直接访问 os.environ
```

**问题**:
- ❌ API Key 存储于配置文件或环境变量
- ❌ Sandbox 内代码可访问环境变量 (凭证暴露)
- ❌ 无凭证保险库概念
- ❌ 无凭证代理机制
- ❌ 无凭证轮换支持
- ❌ 无外部调用审计

---

## 设计方案

### 1. CredentialVault (凭证保险库)

```python
class CredentialVault:
    """凭证保险库
    
    所有凭证存储在独立的加密存储中，Harness 和 Sandbox 无法直接访问
    """
    
    # 凭证类型
    CREDENTIAL_TYPES = {
        "api_key": "API 密钥",
        "oauth_token": "OAuth 令牌",
        "ssh_key": "SSH 密钥",
        "database_password": "数据库密码",
        "cloud_credentials": "云服务凭证",
    }
    
    # 作用域定义
    SCOPE_PERMISSIONS = {
        "api_call": "仅允许 API 调用",
        "file_upload": "允许文件上传",
        "admin": "允许管理操作",
    }
    
    def __init__(self, vault_path: Path, encryption_key: str = None):
        self._vault_path = vault_path
        self._encryption_key = encryption_key or self._generate_encryption_key()
        self._credentials: dict[str, dict] = {}
        self._credential_access_log: list[dict] = []
        self._rotation_schedule: dict[str, dict] = {}
        
        self._init_vault()
    
    def _init_vault(self) -> None:
        """初始化保险库"""
        self._vault_path.mkdir(parents=True, exist_ok=True)
        
        # 加载已有凭证
        self._load_credentials()
        
        # 初始化审计日志
        self._init_audit_log()
    
    # === 凭证管理 ===
    
    def store_credential(
        self,
        provider: str,
        credential_type: str,
        credential_value: str,
        scopes: list[str] = None,
        metadata: dict = None,
    ) -> str:
        """存储凭证
        
        Args:
            provider: 提供商名称 (如 "openai", "aws", "github")
            credential_type: 凭证类型 (如 "api_key")
            credential_value: 凭证值
            scopes: 允许的作用域
            metadata: 元数据 (如 expiry, description)
        
        Returns:
            credential_id
        """
        credential_id = f"{provider}_{credential_type}"
        
        # 加密存储
        encrypted_value = self._encrypt(credential_value)
        
        self._credentials[credential_id] = {
            "provider": provider,
            "type": credential_type,
            "value_encrypted": encrypted_value,
            "scopes": scopes or ["api_call"],
            "metadata": metadata or {},
            "created_at": time.time(),
            "last_accessed": None,
            "access_count": 0,
        }
        
        self._persist_credentials()
        
        logger.info(f"Credential stored: {credential_id}")
        return credential_id
    
    def get_credential(
        self,
        provider: str,
        credential_type: str,
        scope: str = "api_call",
        requester_id: str = None,
    ) -> str:
        """获取凭证
        
        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            scope: 请求的作用域
            requester_id: 请求者 ID (用于审计)
        
        Returns:
            凭证值 (临时解密)
        
        Raises:
            PermissionError: 作用域不允许
        """
        credential_id = f"{provider}_{credential_type}"
        
        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")
        
        credential = self._credentials[credential_id]
        
        # 1. 作用域检查
        if scope not in credential["scopes"]:
            raise PermissionError(
                f"Scope {scope} not allowed for {credential_id}. "
                f"Allowed scopes: {credential['scopes']}"
            )
        
        # 2. 记录访问日志
        self._log_credential_access(credential_id, scope, requester_id)
        
        # 3. 解密凭证 (临时)
        decrypted_value = self._decrypt(credential["value_encrypted"])
        
        # 4. 更新访问统计
        credential["last_accessed"] = time.time()
        credential["access_count"] += 1
        
        return decrypted_value
    
    def rotate_credential(
        self,
        provider: str,
        credential_type: str,
        new_value: str,
    ) -> None:
        """轮换凭证
        
        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            new_value: 新凭证值
        """
        credential_id = f"{provider}_{credential_type}"
        
        if credential_id not in self._credentials:
            raise ValueError(f"Credential not found: {credential_id}")
        
        # 加密新值
        encrypted_value = self._encrypt(new_value)
        
        # 记录轮换历史
        old_value_encrypted = self._credentials[credential_id]["value_encrypted"]
        self._credentials[credential_id]["rotation_history"].append({
            "old_value_encrypted": old_value_encrypted,
            "rotated_at": time.time(),
            "rotated_by": "system",
        })
        
        # 更新凭证
        self._credentials[credential_id]["value_encrypted"] = encrypted_value
        self._credentials[credential_id]["rotated_at"] = time.time()
        
        self._persist_credentials()
        
        logger.info(f"Credential rotated: {credential_id}")
    
    # === 加密/解密 ===
    
    def _encrypt(self, value: str) -> str:
        """加密凭证"""
        from cryptography.fernet import Fernet
        
        fernet = Fernet(self._encryption_key.encode())
        encrypted = fernet.encrypt(value.encode())
        return base64.b64encode(encrypted).decode()
    
    def _decrypt(self, encrypted_value: str) -> str:
        """解密凭证"""
        from cryptography.fernet import Fernet
        
        fernet = Fernet(self._encryption_key.encode())
        decoded = base64.b64decode(encrypted_value.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode()
    
    def _generate_encryption_key(self) -> str:
        """生成加密密钥"""
        from cryptography.fernet import Fernet
        
        key = Fernet.generate_key()
        
        # 存储密钥到安全位置
        key_path = self._vault_path / ".vault_key"
        with open(key_path, "w") as f:
            f.write(key.decode())
        
        # 设置文件权限
        os.chmod(key_path, 0o600)  # 仅 owner 可读写
        
        return key.decode()
    
    # === 审计 ===
    
    def _log_credential_access(
        self,
        credential_id: str,
        scope: str,
        requester_id: str,
    ) -> None:
        """记录凭证访问"""
        log_entry = {
            "timestamp": time.time(),
            "credential_id": credential_id,
            "scope": scope,
            "requester_id": requester_id,
            "action": "get_credential",
        }
        
        self._credential_access_log.append(log_entry)
        self._persist_audit_log()
    
    def get_access_audit_log(self, limit: int = 100) -> list[dict]:
        """获取访问审计日志"""
        return self._credential_access_log[-limit:]
    
    def get_credential_usage_stats(self, credential_id: str) -> dict:
        """获取凭证使用统计"""
        if credential_id not in self._credentials:
            return {}
        
        credential = self._credentials[credential_id]
        
        accesses = [
            log for log in self._credential_access_log
            if log["credential_id"] == credential_id
        ]
        
        return {
            "credential_id": credential_id,
            "provider": credential["provider"],
            "type": credential["type"],
            "total_access_count": credential["access_count"],
            "last_accessed": credential["last_accessed"],
            "recent_accesses": accesses[-10:],
            "created_at": credential["created_at"],
        }
    
    # === 持久化 ===
    
    def _persist_credentials(self) -> None:
        """持久化凭证"""
        credentials_file = self._vault_path / "credentials.json"
        
        with open(credentials_file, "w") as f:
            json.dump(self._credentials, f)
        
        # 设置文件权限
        os.chmod(credentials_file, 0o600)
    
    def _load_credentials(self) -> None:
        """加载凭证"""
        credentials_file = self._vault_path / "credentials.json"
        
        if credentials_file.exists():
            with open(credentials_file, "r") as f:
                self._credentials = json.load(f)
    
    def _persist_audit_log(self) -> None:
        """持久化审计日志"""
        audit_file = self._vault_path / "audit_log.jsonl"
        
        with open(audit_file, "a") as f:
            for entry in self._credential_access_log[-10:]:  # 只追加最近 10 条
                f.write(json.dumps(entry) + "\n")
    
    def _init_audit_log(self) -> None:
        """初始化审计日志"""
        audit_file = self._vault_path / "audit_log.jsonl"
        
        if audit_file.exists():
            with open(audit_file, "r") as f:
                for line in f:
                    self._credential_access_log.append(json.loads(line))
```

### 2. CredentialProxy (凭证代理)

```python
class CredentialProxy:
    """凭证代理
    
    所有外部请求必须通过代理执行，凭证在请求完成后销毁
    """
    
    def __init__(self, vault: CredentialVault):
        self._vault = vault
        self._request_audit_log: list[dict] = []
        self._external_clients: dict[str, Any] = {}
    
    async def execute_external_request(
        self,
        provider: str,
        credential_type: str,
        request_func: Callable,
        request_context: dict,
        requester_id: str = None,
    ) -> dict:
        """代理执行外部请求
        
        流程:
        1. 从 Vault 获取临时凭证
        2. 执行请求
        3. 请求完成后，凭证上下文清理
        4. 记录审计日志
        
        Args:
            provider: 提供商名称
            credential_type: 凭证类型
            request_func: 请求执行函数
            request_context: 请求上下文
            requester_id: 请求者 ID
        
        Returns:
            请求结果
        """
        # 1. 从 Vault 获取临时凭证
        credential = self._vault.get_credential(
            provider,
            credential_type,
            scope="api_call",
            requester_id=requester_id,
        )
        
        # 2. 创建临时客户端 (凭证不存储在 Sandbox)
        temp_client = await self._create_temp_client(provider, credential)
        
        # 3. 执行请求
        start_time = time.time()
        
        try:
            result = await request_func(temp_client, request_context)
            
            # 4. 记录成功审计
            self._log_request(
                provider, credential_type, requester_id,
                "success", time.time() - start_time, request_context
            )
            
            return {
                "status": "success",
                "result": result,
            }
            
        except Exception as e:
            # 记录失败审计
            self._log_request(
                provider, credential_type, requester_id,
                "failed", time.time() - start_time, request_context,
                error=str(e)
            )
            
            return {
                "status": "failed",
                "error": str(e),
            }
            
        finally:
            # 5. 清理临时客户端 (凭证销毁)
            self._cleanup_temp_client(temp_client)
    
    async def _create_temp_client(self, provider: str, credential: str) -> Any:
        """创建临时客户端
        
        重要: 客户端不存储在 Sandbox 中
        """
        if provider == "openai":
            from openai import AsyncOpenAI
            return AsyncOpenAI(api_key=credential)
        
        elif provider == "anthropic":
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=credential)
        
        elif provider == "bailian":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key=credential,
                base_url="https://coding.dashscope.aliyuncs.com/v1"
            )
        
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _cleanup_temp_client(self, client: Any) -> None:
        """清理临时客户端
        
        凭证销毁: 客户端对象被丢弃，凭证不再可用
        """
        # Python 的垃圾回收会自动清理
        # 显式删除引用确保快速回收
        del client
    
    def _log_request(
        self,
        provider: str,
        credential_type: str,
        requester_id: str,
        status: str,
        duration: float,
        request_context: dict,
        error: str = None,
    ) -> None:
        """记录请求审计"""
        log_entry = {
            "timestamp": time.time(),
            "provider": provider,
            "credential_type": credential_type,
            "requester_id": requester_id,
            "status": status,
            "duration_ms": duration * 1000,
            "request_context": request_context,
            "error": error,
        }
        
        self._request_audit_log.append(log_entry)
        self._persist_request_audit()
    
    def get_request_audit_log(self, limit: int = 100) -> list[dict]:
        """获取请求审计日志"""
        return self._request_audit_log[-limit:]
    
    def _persist_request_audit(self) -> None:
        """持久化请求审计"""
        audit_file = self._vault._vault_path / "request_audit.jsonl"
        
        with open(audit_file, "a") as f:
            entry = self._request_audit_log[-1]  # 只追加最新一条
            f.write(json.dumps(entry) + "\n")
```

### 3. 集成到 Harness

```python
class SecureHarness(Harness):
    """带凭证安全的 Harness"""
    
    def __init__(
        self,
        claude: ClaudeClient,
        session: SessionEventStream,
        sandbox: Sandbox,
        vault: CredentialVault,
    ):
        super().__init__(claude, session, sandbox)
        
        self._vault = vault
        self._credential_proxy = CredentialProxy(vault)
    
    async def call_external_api(
        self,
        provider: str,
        request_func: Callable,
        request_context: dict,
    ) -> dict:
        """调用外部 API (通过凭证代理)
        
        Sandbox 中的代码无法直接访问凭证
        """
        return await self._credential_proxy.execute_external_request(
            provider,
            "api_key",
            request_func,
            request_context,
            requester_id=self.session.session_id,
        )
    
    async def call_llm_with_credential_proxy(self, messages: list[dict]) -> dict:
        """调用 LLM (通过凭证代理)"""
        async def request_func(client, context):
            return await client.chat.completions.create(
                model=context["model_id"],
                messages=context["messages"],
            )
        
        return await self.call_external_api(
            provider=self.claude.gateway.config.primary_provider,
            request_func=request_func,
            request_context={
                "model_id": self.claude.model_id,
                "messages": messages,
            },
        )
```

### 4. Sandbox 凭证隔离

```python
class CredentialIsolatedSandbox(Sandbox):
    """凭证隔离的 Sandbox
    
    Sandbox 内的代码无法访问凭证
    """
    
    def __init__(self, isolation_level: str = "process"):
        super().__init__(isolation_level)
        
        # 禁止访问环境变量中的凭证
        self._blocked_env_vars = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "BAILIAN_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
        ]
    
    async def _execute_in_subprocess(self, tool_name: str, args: dict) -> str:
        """进程级隔离执行 (无凭证)"""
        # 创建隔离环境
        isolated_env = os.environ.copy()
        
        # 移除所有凭证环境变量
        for var in self._blocked_env_vars:
            isolated_env.pop(var, None)
        
        # 创建子进程执行
        proc = await asyncio.create_subprocess_exec(
            "python", "-c",
            f"from tools import {tool_name}; print({tool_name}(**{args}))",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=isolated_env,  # 无凭证环境
        )
        
        stdout, stderr = await proc.communicate()
        return stdout.decode() if stdout else stderr.decode()
    
    async def _execute_in_container(self, tool_name: str, args: dict) -> str:
        """Docker 容器级隔离 (无凭证)"""
        import docker
        client = docker.from_env()
        
        # 创建临时容器 (不传递环境变量中的凭证)
        container = client.containers.run(
            "seed-agent-sandbox:latest",
            f"python -c 'from tools import {tool_name}; {tool_name}(**{args})'",
            volumes={str(self._fs_root): {"bind": "/workspace", "mode": "rw"}},
            environment={},  # 不传递任何环境变量
            remove=True,
        )
        
        return container
```

---

## 实施步骤

### Phase 1: CredentialVault 实现 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 实现凭证加密存储 | encrypt/decrypt 正确 |
| 1.2 | 实现作用域检查 | scope permission 正确 |
| 1.3 | 实现凭证轮换 | rotate_credential |
| 1.4 | 实现审计日志 | access_audit_log |

### Phase 2: CredentialProxy 实现 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 实现代理执行 | execute_external_request |
| 2.2 | 实现临时客户端 | create_temp_client |
| 2.3 | 实现凭证销毁 | cleanup_temp_client |
| 2.4 | 实现请求审计 | request_audit_log |

### Phase 3: Sandbox 隔离 (1天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | 实现环境变量过滤 | blocked_env_vars |
| 3.2 | 实现进程级隔离 | isolated_env |
| 3.3 | 实现容器级隔离 | 无凭证环境 |

### Phase 4: Harness 集成 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 4.1 | SecureHarness 实现 | call_external_api |
| 4.2 | LLMGateway 改造 | 通过 proxy 获取凭证 |
| 4.3 | 集成测试 | 凭证不暴露给 Sandbox |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **凭证永不进沙盒** | Sandbox 内代码无法访问凭证 |
| **最小权限原则** | 按作用域获取凭证 |
| **统一轮换** | 支持凭证轮换，不修改代码 |
| **完整审计** | 所有凭证访问和请求可追溯 |
| **安全隔离** | 进程/容器级凭证隔离 |

---

## 测试计划

```python
def test_credential_vault():
    vault = CredentialVault(Path("/tmp/vault"))
    
    # 存储凭证
    vault.store_credential("openai", "api_key", "sk-test123", scopes=["api_call"])
    
    # 获取凭证
    credential = vault.get_credential("openai", "api_key", scope="api_call", requester_id="test")
    assert credential == "sk-test123"
    
    # 作用域检查
    try:
        vault.get_credential("openai", "api_key", scope="admin", requester_id="test")
        assert False, "Should raise PermissionError"
    except PermissionError:
        pass
    
    # 轮换凭证
    vault.rotate_credential("openai", "api_key", "sk-new456")
    credential = vault.get_credential("openai", "api_key", scope="api_call", requester_id="test")
    assert credential == "sk-new456"

def test_credential_proxy():
    vault = CredentialVault(Path("/tmp/vault"))
    vault.store_credential("openai", "api_key", "sk-test123")
    
    proxy = CredentialProxy(vault)
    
    # 代理执行请求
    async def request_func(client, context):
        return {"result": "success"}
    
    result = await proxy.execute_external_request(
        "openai", "api_key", request_func, {"test": "context"}
    )
    
    assert result["status"] == "success"
    
    # 检查审计日志
    audit = proxy.get_request_audit_log()
    assert len(audit) > 0

def test_credential_isolated_sandbox():
    sandbox = CredentialIsolatedSandbox(isolation_level="process")
    
    # 尝试访问环境变量
    result = await sandbox._execute_in_subprocess(
        "code_as_policy",
        {"code": "import os; print(os.environ.get('OPENAI_API_KEY'))"}
    )
    
    # 应返回 None 或空 (凭证被隔离)
    assert "sk-" not in result  # 凭证未暴露
```

---

## 相关文档

- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Sandbox 集成
- [07_tool_permission_risk_design.md](07_tool_permission_risk_design.md) - 工具权限