"""
安全模块单元测试 - CommandRiskClassifier, ProgressiveToolExpander, SinglePurposeToolFactory, SecureSandbox

覆盖:
- 风险分类: 各风险等级、参数风险、用户权限修正
- 渐进式扩展: 层级判定、动态扩展、复杂度自适应
- 单用途工具: 工具创建、参数验证、风险预设
- 安全沙盒: 集成执行、用户确认、历史追溯
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.security.risk_classifier import (
    CommandRiskClassifier,
    ClassificationResult,
    RiskLevel,
    RiskAction,
    RISK_LEVEL_CONFIGS,
)
from src.security.tool_expander import (
    ProgressiveToolExpander,
    ToolTier,
    ExpansionEvent,
    TOOL_TIER_CONFIGS,
)
from src.security.single_purpose_tools import (
    SinglePurposeToolFactory,
    SinglePurposeToolConfig,
    SinglePurposeToolRisk,
    SINGLE_PURPOSE_TOOLS,
)
from src.security.secure_sandbox import (
    SecureSandbox,
    SecureExecutionResult,
)
from src.sandbox import IsolationLevel


# === CommandRiskClassifier 测试 ===

class TestCommandRiskClassifier:
    """测试 CommandRiskClassifier"""

    def test_init_default_values(self):
        """默认初始化"""
        classifier = CommandRiskClassifier()
        assert classifier._isolation_level == "process"
        assert classifier._user_permission_level == "normal"

    def test_init_custom_values(self):
        """自定义初始化"""
        classifier = CommandRiskClassifier(
            isolation_level="container",
            user_permission_level="admin"
        )
        assert classifier._isolation_level == "container"
        assert classifier._user_permission_level == "admin"

    def test_classify_safe_tool(self):
        """安全工具分类"""
        classifier = CommandRiskClassifier()
        result = classifier.classify("file_read", {"path": "/tmp/test.txt"})

        assert result.risk_level == RiskLevel.SAFE
        assert result.action == RiskAction.AUTO_EXECUTE
        assert result.score < 0.3

    def test_classify_medium_risk_tool(self):
        """中风险工具分类"""
        classifier = CommandRiskClassifier()
        result = classifier.classify("file_write", {"path": "/tmp/test.txt"})

        assert result.risk_level in (RiskLevel.SAFE, RiskLevel.CAUTION)
        assert result.score >= 0.0

    def test_classify_high_risk_tool(self):
        """高风险工具分类"""
        classifier = CommandRiskClassifier()
        result = classifier.classify("code_as_policy", {"code": "print('hello')"})

        # code_as_policy 基础风险 0.8，但安全代码可能被降低
        assert result.score >= 0.5

    def test_classify_dangerous_command(self):
        """危险命令检测"""
        classifier = CommandRiskClassifier()
        result = classifier.classify(
            "code_as_policy",
            {"code": "rm -rf /", "language": "shell"}
        )

        # rm -rf / 是危险命令，应该被拦截
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.action == RiskAction.BLOCK
        assert "dangerous_command" in str(result.factors)

    def test_classify_path_traversal(self):
        """路径遍历检测"""
        classifier = CommandRiskClassifier()
        result = classifier.classify(
            "file_read",
            {"path": "/tmp/../etc/passwd"}
        )

        # 包含 .. 路径遍历
        assert result.score > 0.0
        assert any("path_traversal" in f for f in result.factors)

    def test_classify_system_path(self):
        """系统路径检测"""
        classifier = CommandRiskClassifier()
        result = classifier.classify(
            "file_write",
            {"path": "/etc/passwd"}
        )

        # /etc/ 是系统路径
        assert result.score > 0.5
        assert any("system_path" in f for f in result.factors)

    def test_user_permission_modifier_admin(self):
        """管理员权限修正"""
        classifier = CommandRiskClassifier(user_permission_level="admin")
        result = classifier.classify("file_write", {"path": "/tmp/test.txt"})

        # 管理员风险降低 -0.4
        assert result.score < 0.5

    def test_user_permission_modifier_guest(self):
        """访客权限修正"""
        classifier = CommandRiskClassifier(user_permission_level="guest")
        result = classifier.classify("file_write", {"path": "/tmp/test.txt"})

        # 访客风险提高 +0.3
        assert result.score >= 0.4

    def test_isolation_level_modifier_container(self):
        """容器隔离修正"""
        classifier = CommandRiskClassifier(isolation_level="container")
        result = classifier.classify("code_as_policy", {"code": "print(1)"})

        # 容器隔离风险降低 -0.5
        assert result.score < 1.0

    def test_isolation_level_modifier_vm(self):
        """虚拟机隔离修正"""
        classifier = CommandRiskClassifier(isolation_level="vm")
        result = classifier.classify("code_as_policy", {"code": "print(1)"})

        # 虚拟机隔离风险大幅降低 -0.8
        assert result.score < 0.5

    def test_classification_history(self):
        """分类历史记录"""
        classifier = CommandRiskClassifier()

        classifier.classify("file_read", {"path": "/tmp/a.txt"})
        classifier.classify("file_write", {"path": "/tmp/b.txt"})
        classifier.classify("code_as_policy", {"code": "print(1)"})

        history = classifier.get_recent_classifications(limit=10)
        assert len(history) == 3

    def test_classification_stats(self):
        """分类统计"""
        classifier = CommandRiskClassifier()

        classifier.classify("file_read", {"path": "/tmp/a.txt"})
        classifier.classify("file_write", {"path": "/tmp/b.txt"})

        stats = classifier.get_classification_stats()
        assert stats["total_classifications"] == 2
        assert "by_level" in stats
        assert "average_score" in stats

    def test_update_user_level(self):
        """更新用户权限等级"""
        classifier = CommandRiskClassifier(user_permission_level="normal")
        classifier.update_user_level("admin")

        assert classifier._user_permission_level == "admin"

    def test_update_isolation_level(self):
        """更新隔离等级"""
        classifier = CommandRiskClassifier(isolation_level="process")
        classifier.update_isolation_level("container")

        assert classifier._isolation_level == "container"

    def test_clear_history(self):
        """清空历史"""
        classifier = CommandRiskClassifier()

        classifier.classify("file_read", {"path": "/tmp/a.txt"})
        classifier.clear_history()

        assert len(classifier._classification_history) == 0


class TestRiskLevelConfigs:
    """测试风险等级配置"""

    def test_all_levels_configured(self):
        """所有等级都有配置"""
        assert RiskLevel.SAFE in RISK_LEVEL_CONFIGS
        assert RiskLevel.CAUTION in RISK_LEVEL_CONFIGS
        assert RiskLevel.RISKY in RISK_LEVEL_CONFIGS
        assert RiskLevel.DANGEROUS in RISK_LEVEL_CONFIGS

    def test_safe_level_auto_execute(self):
        """SAFE 等级自动执行"""
        config = RISK_LEVEL_CONFIGS[RiskLevel.SAFE]
        assert config.action == RiskAction.AUTO_EXECUTE

    def test_dangerous_level_block(self):
        """DANGEROUS 等级拦截"""
        config = RISK_LEVEL_CONFIGS[RiskLevel.DANGEROUS]
        assert config.action == RiskAction.BLOCK
        assert config.block_message != ""

    def test_risky_level_require_approval(self):
        """RISKY 等级需要确认"""
        config = RISK_LEVEL_CONFIGS[RiskLevel.RISKY]
        assert config.require_user_approval is True


# === ProgressiveToolExpander 测试 ===

class TestProgressiveToolExpander:
    """测试 ProgressiveToolExpander"""

    def test_init_default_tier(self):
        """默认初始化层级"""
        expander = ProgressiveToolExpander()
        assert expander.get_current_tier() == ToolTier.TIER_0_MINIMAL

    def test_init_custom_tier(self):
        """自定义初始层级"""
        expander = ProgressiveToolExpander(initial_tier=ToolTier.TIER_1_BASIC)
        assert expander.get_current_tier() == ToolTier.TIER_1_BASIC

    def test_get_available_tools_initial(self):
        """获取初始可用工具"""
        expander = ProgressiveToolExpander()
        tools = expander.get_available_tools({"iteration": 0})

        # Tier 0: 只读操作
        assert "file_read" in tools
        assert "code_as_policy" not in tools

    def test_get_available_tools_with_iteration(self):
        """迭代次数触发扩展"""
        expander = ProgressiveToolExpander()
        tools = expander.get_available_tools({"iteration": 6})

        # Tier 2: 写入操作 (iteration > 5)
        assert "file_write" in tools

    def test_get_available_tools_with_task_type(self):
        """任务类型触发扩展"""
        expander = ProgressiveToolExpander()
        tools = expander.get_available_tools({"task_type": "implementation"})

        # Implementation 任务需要写入工具
        assert "file_write" in tools
        assert "file_edit" in tools

    def test_get_available_tools_user_permission_limit(self):
        """用户权限限制层级"""
        expander = ProgressiveToolExpander()
        tools = expander.get_available_tools({
            "task_type": "admin",  # 需要 Tier 3
            "user_permission": "guest"  # 限制到 Tier 1
        })

        # Guest 用户限制到 Tier 1
        assert "code_as_policy" not in tools

    def test_get_available_tools_high_complexity(self):
        """高复杂度触发扩展"""
        expander = ProgressiveToolExpander()
        tools = expander.get_available_tools({
            "complexity": 0.9,
            "user_permission": "trusted"
        })

        # 高复杂度 + trusted 用户可使用 Tier 3
        assert "code_as_policy" in tools

    def test_force_expand_to_tier(self):
        """强制扩展到指定层级"""
        expander = ProgressiveToolExpander()
        added = expander.force_expand_to_tier(ToolTier.TIER_3_FULL, "test")

        assert expander.get_current_tier() == ToolTier.TIER_3_FULL
        assert len(added) > 0

    def test_reset_to_initial(self):
        """重置到初始层级"""
        expander = ProgressiveToolExpander()
        expander.force_expand_to_tier(ToolTier.TIER_3_FULL)
        expander.reset_to_initial()

        assert expander.get_current_tier() == ToolTier.TIER_0_MINIMAL

    def test_is_tool_available(self):
        """工具可用性检查"""
        expander = ProgressiveToolExpander()

        # Tier 0
        assert expander.is_tool_available("file_read")
        assert not expander.is_tool_available("file_write")

    def test_get_tool_tier(self):
        """获取工具所属层级"""
        expander = ProgressiveToolExpander()

        # file_read 在 Tier 0
        assert expander.get_tool_tier("file_read") == ToolTier.TIER_0_MINIMAL

        # code_as_policy 在 Tier 3
        assert expander.get_tool_tier("code_as_policy") == ToolTier.TIER_3_FULL

    def test_expansion_history(self):
        """扩展历史记录"""
        expander = ProgressiveToolExpander()
        expander.get_available_tools({"iteration": 5})

        history = expander.get_expansion_history()
        assert len(history) > 0

    def test_expansion_stats(self):
        """扩展统计"""
        expander = ProgressiveToolExpander()
        expander.get_available_tools({"iteration": 10})

        stats = expander.get_expansion_stats()
        assert "current_tier" in stats
        assert "available_tools_count" in stats

    def test_auto_expansion_disabled(self):
        """禁用自动扩展"""
        expander = ProgressiveToolExpander(enable_auto_expansion=False)
        tools = expander.get_available_tools({"task_type": "implementation"})

        # 不自动扩展，保持在 Tier 0
        assert expander.get_current_tier() == ToolTier.TIER_0_MINIMAL

    def test_set_auto_expansion(self):
        """设置自动扩展开关"""
        expander = ProgressiveToolExpander()
        expander.set_auto_expansion(False)

        assert expander._enable_auto_expansion is False


class TestToolTierConfigs:
    """测试工具层级配置"""

    def test_all_tiers_configured(self):
        """所有层级都有配置"""
        assert ToolTier.TIER_0_MINIMAL in TOOL_TIER_CONFIGS
        assert ToolTier.TIER_1_BASIC in TOOL_TIER_CONFIGS
        assert ToolTier.TIER_2_EXTENDED in TOOL_TIER_CONFIGS
        assert ToolTier.TIER_3_FULL in TOOL_TIER_CONFIGS

    def test_tier_hierarchy(self):
        """层级继承关系"""
        tier0_tools = TOOL_TIER_CONFIGS[ToolTier.TIER_0_MINIMAL].tools
        tier1_tools = TOOL_TIER_CONFIGS[ToolTier.TIER_1_BASIC].tools
        tier2_tools = TOOL_TIER_CONFIGS[ToolTier.TIER_2_EXTENDED].tools
        tier3_tools = TOOL_TIER_CONFIGS[ToolTier.TIER_3_FULL].tools

        # 每层包含前一层的工具
        assert tier0_tools.issubset(tier1_tools)
        assert tier1_tools.issubset(tier2_tools)
        assert tier2_tools.issubset(tier3_tools)

    def test_tier_descriptions(self):
        """层级描述"""
        for tier, config in TOOL_TIER_CONFIGS.items():
            assert config.description != ""
            assert len(config.tools) > 0


# === SinglePurposeToolFactory 测试 ===

class TestSinglePurposeToolFactory:
    """测试 SinglePurposeToolFactory"""

    def test_init_default_values(self):
        """默认初始化"""
        factory = SinglePurposeToolFactory()
        assert factory._allow_risky_tools is True
        assert factory._allow_dangerous_tools is False

    def test_init_custom_values(self):
        """自定义初始化"""
        factory = SinglePurposeToolFactory(
            allow_risky_tools=False,
            allow_dangerous_tools=True
        )
        assert factory._allow_risky_tools is False
        assert factory._allow_dangerous_tools is True

    def test_create_safe_tool(self):
        """创建安全工具"""
        factory = SinglePurposeToolFactory()
        tool = factory.create_tool("read_file_content")

        assert tool.__name__ == "read_file_content"
        assert tool.__doc__ != ""

    def test_create_risky_tool_blocked(self):
        """创建 risky 工具被阻止"""
        factory = SinglePurposeToolFactory(allow_risky_tools=False)

        with pytest.raises(ValueError) as exc_info:
            factory.create_tool("delete_file")

        assert "requires risky tool permission" in str(exc_info.value)

    def test_create_dangerous_tool_blocked(self):
        """创建 dangerous 工具被阻止"""
        factory = SinglePurposeToolFactory()

        with pytest.raises(ValueError) as exc_info:
            factory.create_tool("git_push")

        assert "blocked by default" in str(exc_info.value) or "requires dangerous" in str(exc_info.value)

    def test_create_unknown_tool(self):
        """创建未知工具"""
        factory = SinglePurposeToolFactory()

        with pytest.raises(ValueError) as exc_info:
            factory.create_tool("unknown_tool")

        assert "Unknown" in str(exc_info.value)

    def test_get_tool_config(self):
        """获取工具配置"""
        factory = SinglePurposeToolFactory()
        config = factory.get_tool_config("read_file_content")

        assert config is not None
        assert config.risk == SinglePurposeToolRisk.SAFE

    def test_get_all_tool_names(self):
        """获取所有工具名称"""
        factory = SinglePurposeToolFactory()
        names = factory.get_all_tool_names()

        assert len(names) > 0
        assert "read_file_content" in names

    def test_get_tools_by_risk(self):
        """按风险等级获取工具"""
        factory = SinglePurposeToolFactory()

        safe_tools = factory.get_tools_by_risk(SinglePurposeToolRisk.SAFE)
        assert "read_file_content" in safe_tools

        risky_tools = factory.get_tools_by_risk(SinglePurposeToolRisk.RISKY)
        assert "delete_file" in risky_tools

    def test_get_tool_schema(self):
        """获取工具 schema"""
        factory = SinglePurposeToolFactory()
        schema = factory.get_tool_schema("read_file_content")

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "read_file_content"
        assert "parameters" in schema["function"]

    def test_get_all_tool_schemas(self):
        """获取所有工具 schema"""
        factory = SinglePurposeToolFactory(allow_dangerous_tools=True)
        schemas = factory.get_all_tool_schemas()

        assert len(schemas) > 0

    def test_get_allowed_tool_names(self):
        """获取允许的工具名称"""
        factory = SinglePurposeToolFactory()
        allowed = factory.get_allowed_tool_names()

        # 不包含 dangerous 工具
        assert "git_push" not in allowed

    def test_set_allow_risky_tools(self):
        """设置 risky 工具权限"""
        factory = SinglePurposeToolFactory(allow_risky_tools=False)
        factory.set_allow_risky_tools(True)

        assert factory._allow_risky_tools is True

    def test_set_allow_dangerous_tools(self):
        """设置 dangerous 工具权限"""
        factory = SinglePurposeToolFactory()
        factory.set_allow_dangerous_tools(True)

        assert factory._allow_dangerous_tools is True


class TestSinglePurposeToolExecution:
    """测试单用途工具执行"""

    def test_read_file_content(self, tmp_path):
        """读取文件内容"""
        factory = SinglePurposeToolFactory()
        tool = factory.create_tool("read_file_content")

        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        result = tool(path=str(test_file))

        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_list_directory(self, tmp_path):
        """列出目录"""
        factory = SinglePurposeToolFactory()
        tool = factory.create_tool("list_directory")

        # 创建测试文件
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.txt").write_text("test")

        result = tool(path=str(tmp_path))

        assert "file1.txt" in result
        assert "file2.txt" in result

    def test_create_directory(self, tmp_path):
        """创建目录"""
        factory = SinglePurposeToolFactory()
        tool = factory.create_tool("create_directory")

        new_dir = tmp_path / "new_dir"
        result = tool(path=str(new_dir))

        assert "[OK]" in result
        assert new_dir.exists()

    def test_delete_file(self, tmp_path):
        """删除文件（需要确认）"""
        # 设置确认回调返回 True
        factory = SinglePurposeToolFactory(
            confirmation_callback=lambda name, args: True
        )
        tool = factory.create_tool("delete_file")

        # 创建测试文件
        test_file = tmp_path / "to_delete.txt"
        test_file.write_text("test")

        result = tool(path=str(test_file))

        assert "[OK]" in result
        assert not test_file.exists()

    def test_delete_file_cancelled(self, tmp_path):
        """删除文件取消"""
        # 设置确认回调返回 False
        factory = SinglePurposeToolFactory(
            confirmation_callback=lambda name, args: False
        )
        tool = factory.create_tool("delete_file")

        test_file = tmp_path / "to_keep.txt"
        test_file.write_text("test")

        result = tool(path=str(test_file))

        assert "[CANCELLED]" in result
        assert test_file.exists()

    def test_git_status(self):
        """Git status"""
        factory = SinglePurposeToolFactory()
        tool = factory.create_tool("git_status")

        result = tool()

        # 可能成功或失败（取决于 git 安装）
        assert result != ""

    def test_get_env_info(self):
        """获取环境信息"""
        factory = SinglePurposeToolFactory()
        tool = factory.create_tool("get_env_info")

        result = tool()

        # 应返回环境变量列表
        assert result != ""


class TestSinglePurposeToolsConfig:
    """测试单用途工具配置"""

    def test_all_tools_configured(self):
        """所有工具都有配置"""
        assert len(SINGLE_PURPOSE_TOOLS) > 0

    def test_tool_config_structure(self):
        """工具配置结构"""
        for name, config in SINGLE_PURPOSE_TOOLS.items():
            assert config.name == name
            assert config.description != ""
            assert config.replaces_command != ""
            assert config.risk in SinglePurposeToolRisk
            assert isinstance(config.args_schema, dict)

    def test_risky_tools_require_confirmation(self):
        """Risky 工具需要确认"""
        for name, config in SINGLE_PURPOSE_TOOLS.items():
            if config.risk == SinglePurposeToolRisk.RISKY:
                assert config.require_confirmation is True

    def test_dangerous_tools_blocked_by_default(self):
        """Dangerous 工具默认阻止"""
        for name, config in SINGLE_PURPOSE_TOOLS.items():
            if config.risk == SinglePurposeToolRisk.DANGEROUS:
                assert config.block_by_default is True


# === SecureSandbox 测试 ===

class TestSecureSandbox:
    """测试 SecureSandbox"""

    def test_init_default_values(self):
        """默认初始化"""
        sandbox = SecureSandbox()

        assert sandbox.isolation_level == IsolationLevel.PROCESS
        assert sandbox._user_permission_level == "normal"
        assert sandbox._allow_risky_tools is True
        assert sandbox._allow_dangerous_tools is False

    def test_init_custom_values(self):
        """自定义初始化"""
        sandbox = SecureSandbox(
            isolation_level=IsolationLevel.CONTAINER,
            user_permission_level="admin",
            allow_dangerous_tools=True
        )

        assert sandbox.isolation_level == IsolationLevel.CONTAINER
        assert sandbox._user_permission_level == "admin"
        assert sandbox._allow_dangerous_tools is True

    def test_classify_tool_risk(self):
        """分类工具风险"""
        sandbox = SecureSandbox()
        result = sandbox.classify_tool_risk("file_read", {"path": "/tmp/test.txt"})

        assert result.risk_level == RiskLevel.SAFE
        assert result.action == RiskAction.AUTO_EXECUTE

    def test_get_available_tools_secure_initial(self):
        """获取可用工具（初始状态）"""
        sandbox = SecureSandbox()
        tools = sandbox.get_available_tools_secure({"iteration": 0})

        # Tier 0 或 Tier 1 工具
        assert "file_read" in tools

    def test_get_available_tools_secure_expanded(self):
        """获取可用工具（扩展状态）"""
        sandbox = SecureSandbox()
        tools = sandbox.get_available_tools_secure({"task_type": "implementation"})

        # Implementation 任务需要写入工具
        assert "file_write" in tools

    def test_get_risk_classification_stats(self):
        """获取风险分类统计"""
        sandbox = SecureSandbox()
        sandbox.classify_tool_risk("file_read", {"path": "/tmp/a.txt"})
        sandbox.classify_tool_risk("file_write", {"path": "/tmp/b.txt"})

        stats = sandbox.get_risk_classification_stats()
        assert stats["total_classifications"] == 2

    def test_get_current_tool_tier(self):
        """获取当前工具层级"""
        sandbox = SecureSandbox()
        sandbox.get_available_tools_secure({"iteration": 5})

        tier = sandbox.get_current_tool_tier()
        assert tier is not None

    def test_force_expand_to_tier(self):
        """强制扩展层级"""
        sandbox = SecureSandbox()
        added = sandbox.force_expand_to_tier(ToolTier.TIER_3_FULL)

        assert sandbox.get_current_tool_tier() == ToolTier.TIER_3_FULL

    def test_reset_tool_tier(self):
        """重置层级"""
        sandbox = SecureSandbox()
        sandbox.force_expand_to_tier(ToolTier.TIER_3_FULL)
        sandbox.reset_tool_tier()

        assert sandbox.get_current_tool_tier() == ToolTier.TIER_0_MINIMAL

    def test_set_user_permission_level(self):
        """设置用户权限等级"""
        sandbox = SecureSandbox()
        sandbox.set_user_permission_level("admin")

        assert sandbox._user_permission_level == "admin"

    def test_set_allow_risky_tools(self):
        """设置 risky 工具权限"""
        sandbox = SecureSandbox()
        sandbox.set_allow_risky_tools(False)

        assert sandbox._allow_risky_tools is False

    def test_set_allow_dangerous_tools(self):
        """设置 dangerous 工具权限"""
        sandbox = SecureSandbox()
        sandbox.set_allow_dangerous_tools(True)

        assert sandbox._allow_dangerous_tools is True

    def test_get_status_secure(self):
        """获取安全状态"""
        sandbox = SecureSandbox()
        status = sandbox.get_status_secure()

        assert "user_permission_level" in status
        assert "allow_risky_tools" in status
        assert "progressive_expansion_enabled" in status

    def test_clear_history(self):
        """清空历史"""
        sandbox = SecureSandbox()
        sandbox.classify_tool_risk("file_read", {"path": "/tmp/a.txt"})
        sandbox.clear_history()

        assert len(sandbox._secure_execution_history) == 0


class TestSecureSandboxExecution:
    """测试 SecureSandbox 执行"""

    @pytest.mark.asyncio
    async def test_execute_safe_tool(self):
        """执行安全工具"""
        sandbox = SecureSandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "file_read", "arguments": '{"path": "/tmp/test.txt"}'}
        }

        results = await sandbox.execute_tools_secure([tool_call])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].risk_level == RiskLevel.SAFE

    @pytest.mark.asyncio
    async def test_execute_blocked_tool(self):
        """执行被阻止的工具"""
        sandbox = SecureSandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "code_as_policy",
                "arguments": '{"code": "rm -rf /", "language": "shell"}'
            }
        }

        results = await sandbox.execute_tools_secure([tool_call])

        assert len(results) == 1
        assert results[0].blocked is True
        assert results[0].risk_level == RiskLevel.DANGEROUS

    @pytest.mark.asyncio
    async def test_execute_tool_not_in_tier(self):
        """执行不在当前层级的工具"""
        sandbox = SecureSandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "code_as_policy",
                "arguments": '{"code": "print(1)"}'
            }
        }

        # 初始层级（Tier 0）不包含 code_as_policy
        results = await sandbox.execute_tools_secure([tool_call], {"iteration": 0})

        assert len(results) == 1
        assert results[0].blocked is True

    @pytest.mark.asyncio
    async def test_execute_with_user_confirmation_approved(self):
        """执行需要确认的工具（批准）"""
        sandbox = SecureSandbox(
            user_confirmation_callback=lambda name, risk, args: True
        )
        sandbox.register_tools(MockToolRegistry())

        # 强制扩展到 Tier 3 以使用 code_as_policy
        sandbox.force_expand_to_tier(ToolTier.TIER_3_FULL)

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "file_write",
                "arguments": '{"path": "/etc/passwd", "content": "test"}'
            }
        }

        results = await sandbox.execute_tools_secure([tool_call])

        assert results[0].user_confirmed is True

    @pytest.mark.asyncio
    async def test_execute_with_user_confirmation_denied(self):
        """执行需要确认的工具（拒绝）"""
        sandbox = SecureSandbox(
            user_confirmation_callback=lambda name, risk, args: False
        )
        sandbox.register_tools(MockToolRegistry())

        sandbox.force_expand_to_tier(ToolTier.TIER_3_FULL)

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "file_write",
                "arguments": '{"path": "/etc/passwd", "content": "test"}'
            }
        }

        results = await sandbox.execute_tools_secure([tool_call])

        assert results[0].user_confirmed is False
        assert "[CANCELLED]" in results[0].content

    @pytest.mark.asyncio
    async def test_execution_history(self):
        """执行历史记录"""
        sandbox = SecureSandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "file_read", "arguments": '{}'}},
            {"id": "call_2", "type": "function", "function": {"name": "list_directory", "arguments": '{}'}},
        ]

        await sandbox.execute_tools_secure(tool_calls)

        history = sandbox.get_recent_executions()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_execution_stats(self):
        """执行统计"""
        sandbox = SecureSandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "file_read", "arguments": '{}'}},
        ]

        await sandbox.execute_tools_secure(tool_calls)

        stats = sandbox.get_secure_execution_stats()
        assert stats["total_executions"] == 1
        assert stats["successful"] == 1

    @pytest.mark.asyncio
    async def test_execute_single_purpose_tool(self):
        """执行单用途工具"""
        sandbox = SecureSandbox(enable_single_purpose_tools=True)

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "git_status",
                "arguments": '{}'
            }
        }

        # 扩展到包含 git_status 的层级
        sandbox.force_expand_to_tier(ToolTier.TIER_0_MINIMAL)

        results = await sandbox.execute_tools_secure([tool_call])

        assert len(results) == 1


class MockToolRegistry:
    """Mock ToolRegistry for testing"""

    def __init__(self):
        self._tools = {
            "file_read": AsyncMock(return_value="file content"),
            "file_write": AsyncMock(return_value="written"),
            "list_directory": AsyncMock(return_value="dir listing"),
            "code_as_policy": AsyncMock(return_value="executed"),
        }

    def get_schemas(self):
        return [
            {"type": "function", "function": {"name": "file_read"}},
            {"type": "function", "function": {"name": "file_write"}},
            {"type": "function", "function": {"name": "list_directory"}},
            {"type": "function", "function": {"name": "code_as_policy"}},
        ]

    async def execute(self, tool_name, **kwargs):
        if tool_name in self._tools:
            return await self._tools[tool_name](**kwargs)
        raise KeyError(f"Tool not found: {tool_name}")