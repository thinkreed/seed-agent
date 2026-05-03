"""
安全模块 - 工具权限、命令风险分类、凭证安全

包含:
- CommandRiskClassifier: 命令风险分类器
- ProgressiveToolExpander: 渐进式工具扩展
- SinglePurposeToolFactory: 单用途工具工厂
- SecureSandbox: 安全沙盒（集成风险分类）
- CredentialVault: 凭证保险库（加密存储）
- CredentialProxy: 凭证代理（安全请求执行）
- CredentialIsolatedSandbox: 凭证隔离沙盒（环境变量过滤）
- SecureHarness: 安全 Harness（凭证代理集成）

凭证安全架构 (Harness Engineering 设计理念):
- 凭证永不进沙盒：所有凭证存储在独立的 Vault 中
- 按需获取凭证：通过 Proxy 从 Vault 获取临时凭证
- 凭证自动销毁：请求完成后立即清理
- 最小权限原则：按作用域获取凭证
- 完整审计：所有凭证访问可追溯
"""

from src.security.credential_isolated_sandbox import CredentialIsolatedSandbox
from src.security.credential_proxy import CredentialProxy
from src.security.credential_vault import (
    CredentialScope,
    CredentialType,
    CredentialVault,
)
from src.security.risk_classifier import CommandRiskClassifier, RiskAction, RiskLevel
from src.security.secure_harness import SecureHarness
from src.security.secure_sandbox import SecureSandbox
from src.security.single_purpose_tools import SinglePurposeToolFactory
from src.security.tool_expander import ProgressiveToolExpander, ToolTier

__all__ = [
    # 风险分类
    "CommandRiskClassifier",
    "RiskLevel",
    "RiskAction",
    # 工具扩展
    "ProgressiveToolExpander",
    "ToolTier",
    "SinglePurposeToolFactory",
    # 安全沙盒
    "SecureSandbox",
    # 凭证安全
    "CredentialVault",
    "CredentialType",
    "CredentialScope",
    "CredentialProxy",
    "CredentialIsolatedSandbox",
    "SecureHarness",
]
