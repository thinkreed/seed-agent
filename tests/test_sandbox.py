"""
Tests for src/sandbox.py - 三件套工作台

Coverage targets:
- Sandbox initialization
- Path mapping (_map_paths, _map_single_path, reverse_map_path)
- Permission checking (_check_permission)
- Tool execution (execute_tools)
- Permission management (set_permission, get_permissions)
- Isolation levels
- Output truncation
- Credential proxy
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sandbox import (
    Sandbox,
    IsolationLevel,
    PermissionAction,
    SandboxPermission,
    ExecutionResult,
    DEFAULT_SANDBOX_ROOT,
)


class MockToolRegistry:
    """Mock ToolRegistry for testing"""
    def __init__(self):
        self._tools = {
            "test_tool": AsyncMock(return_value="tool result"),
            "file_read": AsyncMock(return_value="file content"),
            "file_write": AsyncMock(return_value="written"),
        }
        self._tool_schemas = [
            {"type": "function", "function": {"name": "test_tool"}},
            {"type": "function", "function": {"name": "file_read"}},
        ]

    def get_schemas(self):
        return self._tool_schemas

    async def execute(self, tool_name, **kwargs):
        if tool_name in self._tools:
            return await self._tools[tool_name](**kwargs)
        raise KeyError(f"Tool not found: {tool_name}")


class TestSandboxInit:
    """Test Sandbox initialization"""

    def test_init_default_values(self):
        """Test initialization with default values"""
        sandbox = Sandbox()

        assert sandbox.isolation_level == IsolationLevel.PROCESS
        assert sandbox._fs_root == DEFAULT_SANDBOX_ROOT
        assert sandbox._network_policy == {"allow": ["*"], "deny": []}

    def test_init_custom_isolation(self):
        """Test initialization with custom isolation level"""
        sandbox = Sandbox(isolation_level=IsolationLevel.CONTAINER)

        assert sandbox.isolation_level == IsolationLevel.CONTAINER

    def test_init_custom_fs_root(self, tmp_path):
        """Test initialization with custom fs_root"""
        sandbox = Sandbox(file_system_root=tmp_path)

        assert sandbox._fs_root == tmp_path

    def test_init_custom_workspace(self, tmp_path):
        """Test initialization with custom workspace"""
        sandbox = Sandbox(workspace_path=tmp_path)

        assert sandbox._workspace_path == tmp_path

    def test_sandbox_dir_created(self, tmp_path):
        """Test sandbox directory is created"""
        sandbox_path = tmp_path / "new_sandbox"
        sandbox = Sandbox(file_system_root=sandbox_path)

        assert sandbox_path.exists()

    def test_init_custom_network_policy(self):
        """Test initialization with custom network policy"""
        policy = {"allow": ["localhost"], "deny": ["*"]}
        sandbox = Sandbox(network_policy=policy)

        assert sandbox._network_policy == policy


class TestPathMapping:
    """Test Sandbox path mapping"""

    def test_map_workspace_path(self):
        """Test mapping workspace path"""
        sandbox = Sandbox(workspace_path=Path("/home/user/project"))

        mapped = sandbox._map_single_path("/workspace/file.txt")
        assert mapped == str(Path("/home/user/project/file.txt"))

    def test_map_sandbox_path(self):
        """Test mapping sandbox path"""
        sandbox = Sandbox(file_system_root=Path("/home/user/.seed/sandbox"))

        mapped = sandbox._map_single_path("/sandbox/data.txt")
        assert mapped == str(Path("/home/user/.seed/sandbox/data.txt"))

    def test_map_root_path(self):
        """Test mapping root path"""
        sandbox = Sandbox(file_system_root=Path("/home/user/.seed/sandbox"))

        mapped = sandbox._map_single_path("/tmp/file.txt")
        assert mapped == str(Path("/home/user/.seed/sandbox/tmp/file.txt"))

    def test_map_relative_path(self):
        """Test mapping relative path (unchanged)"""
        sandbox = Sandbox()

        mapped = sandbox._map_single_path("relative/path.txt")
        assert mapped == "relative/path.txt"

    def test_map_paths_dict(self):
        """Test mapping paths in dict"""
        sandbox = Sandbox(workspace_path=Path("/workspace"))

        args = {
            "path": "/workspace/file.txt",
            "other": "value",
            "nested": {"path": "/workspace/nested.txt"}
        }
        mapped = sandbox._map_paths(args)

        assert mapped["path"] == str(Path("/workspace/file.txt"))
        assert mapped["other"] == "value"
        assert mapped["nested"]["path"] == str(Path("/workspace/nested.txt"))

    def test_map_paths_list(self):
        """Test mapping paths in list"""
        sandbox = Sandbox(workspace_path=Path("/workspace"))

        args = {"paths": ["/workspace/a.txt", "/workspace/b.txt"]}
        mapped = sandbox._map_paths(args)

        # List should be processed but path keys are specific
        assert isinstance(mapped["paths"], list)

    def test_reverse_map_workspace_path(self):
        """Test reverse mapping workspace path"""
        sandbox = Sandbox(workspace_path=Path("/home/user/project"))

        reversed_path = sandbox.reverse_map_path(str(Path("/home/user/project/file.txt")))
        assert reversed_path == "/workspace/file.txt"

    def test_reverse_map_sandbox_path(self):
        """Test reverse mapping sandbox path"""
        sandbox = Sandbox(file_system_root=Path("/home/user/.seed/sandbox"))

        reversed_path = sandbox.reverse_map_path(str(Path("/home/user/.seed/sandbox/data.txt")))
        assert reversed_path == "/sandbox/data.txt"

    def test_reverse_map_external_path(self):
        """Test reverse mapping external path"""
        sandbox = Sandbox(workspace_path=Path("/workspace"))

        reversed_path = sandbox.reverse_map_path("/external/path.txt")
        assert reversed_path == "/external/path.txt"


class TestPermissionChecking:
    """Test Sandbox permission checking"""

    def test_default_permission_allow(self):
        """Test default permissions allow known tools"""
        sandbox = Sandbox()

        assert sandbox._check_permission("file_read", {"path": "/test"})
        assert sandbox._check_permission("file_write", {"path": "/test"})
        assert sandbox._check_permission("run_shell_command", {"path": "/test"})

    def test_unknown_tool_allowed_by_default(self):
        """Test unknown tools are allowed by default"""
        sandbox = Sandbox()

        assert sandbox._check_permission("unknown_tool", {})

    def test_permission_deny(self):
        """Test denying a tool"""
        sandbox = Sandbox()
        sandbox.set_permission("file_write", PermissionAction.DENY)

        assert not sandbox._check_permission("file_write", {"path": "/test"})

    def test_permission_allow_explicit(self):
        """Test explicitly allowing a tool"""
        sandbox = Sandbox()
        sandbox.set_permission("custom_tool", PermissionAction.ALLOW)

        assert sandbox._check_permission("custom_tool", {})

    def test_get_permissions(self):
        """Test getting all permissions"""
        sandbox = Sandbox()
        sandbox.set_permission("test_tool", PermissionAction.DENY)

        perms = sandbox.get_permissions()
        assert "test_tool" in perms
        assert perms["test_tool"]["action"] == "deny"

    def test_permission_with_path_patterns(self):
        """Test permission with path patterns"""
        sandbox = Sandbox()
        sandbox.set_permission(
            "file_read",
            PermissionAction.ALLOW,
            path_patterns=["/workspace/*"]
        )

        assert sandbox._check_permission("file_read", {"path": "/workspace/test.txt"})
        assert not sandbox._check_permission("file_read", {"path": "/other/test.txt"})

    def test_permission_max_output_size(self):
        """Test permission max_output_size"""
        sandbox = Sandbox()
        sandbox.set_permission(
            "test_tool",
            PermissionAction.ALLOW,
            max_output_size=500
        )

        perm = sandbox._permissions["test_tool"]
        assert perm.max_output_size == 500


class TestToolExecution:
    """Test Sandbox tool execution"""

    @pytest.mark.asyncio
    async def test_execute_single_tool(self):
        """Test executing a single tool"""
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_call = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_tool",
                "arguments": "{}"
            }
        }

        results = await sandbox.execute_tools([tool_call])

        assert len(results) == 1
        assert results[0]["tool_call_id"] == "call_123"
        assert results[0]["role"] == "tool"
        assert "tool result" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_execute_multiple_tools(self):
        """Test executing multiple tools"""
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "test_tool", "arguments": "{}"}},
            {"id": "call_2", "type": "function", "function": {"name": "file_read", "arguments": '{"path": "/test"}'}},
        ]

        results = await sandbox.execute_tools(tool_calls)

        assert len(results) == 2
        assert results[0]["tool_call_id"] == "call_1"
        assert results[1]["tool_call_id"] == "call_2"

    @pytest.mark.asyncio
    async def test_execute_tool_with_path_mapping(self):
        """Test tool execution with path mapping"""
        sandbox = Sandbox(workspace_path=Path("/workspace"))
        sandbox.register_tools(MockToolRegistry())

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "file_read",
                "arguments": '{"path": "/workspace/test.txt"}'
            }
        }

        results = await sandbox.execute_tools([tool_call])

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_execute_denied_tool(self):
        """Test executing denied tool"""
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())
        sandbox.set_permission("test_tool", PermissionAction.DENY)

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "test_tool", "arguments": "{}"}
        }

        results = await sandbox.execute_tools([tool_call])

        assert "Permission denied" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_execute_tool_invalid_args(self):
        """Test executing tool with invalid JSON args"""
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "test_tool",
                "arguments": "invalid json"
            }
        }

        results = await sandbox.execute_tools([tool_call])

        assert "Error" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self):
        """Test executing tool that raises exception"""
        sandbox = Sandbox()
        registry = MockToolRegistry()
        registry._tools["test_tool"] = AsyncMock(side_effect=Exception("Tool error"))
        sandbox.register_tools(registry)

        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "test_tool", "arguments": "{}"}
        }

        results = await sandbox.execute_tools([tool_call])

        assert "Error" in results[0]["content"]
        assert "Tool error" in results[0]["content"]


class TestToolRegistry:
    """Test Sandbox tool registry integration"""

    def test_register_tools(self):
        """Test registering tools"""
        sandbox = Sandbox()
        registry = MockToolRegistry()
        sandbox.register_tools(registry)

        assert sandbox._tools == registry

    def test_get_tool_schemas(self):
        """Test getting tool schemas"""
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        schemas = sandbox.get_tool_schemas()
        assert len(schemas) == 2

    def test_get_tool_schemas_empty(self):
        """Test getting tool schemas when none registered"""
        sandbox = Sandbox()

        schemas = sandbox.get_tool_schemas()
        assert schemas == []

    def test_get_registered_tool_names(self):
        """Test getting registered tool names"""
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        names = sandbox.get_registered_tool_names()
        assert "test_tool" in names
        assert "file_read" in names


class TestPermissionModes:
    """Test Sandbox permission modes"""

    def test_deny_all_tools(self):
        """Test denying all tools"""
        sandbox = Sandbox()
        sandbox.deny_all_tools()

        perms = sandbox._permissions
        for perm in perms.values():
            assert perm.action == PermissionAction.DENY

    def test_allow_readonly_tools(self):
        """Test allowing only readonly tools"""
        sandbox = Sandbox()
        sandbox.allow_readonly_tools()

        # Readonly tools should be allowed
        assert sandbox._permissions["file_read"].action == PermissionAction.ALLOW
        assert sandbox._permissions["list_directory"].action == PermissionAction.ALLOW

        # Write tools should be denied
        assert sandbox._permissions["file_write"].action == PermissionAction.DENY
        assert sandbox._permissions["file_edit"].action == PermissionAction.DENY


class TestSandboxStatus:
    """Test Sandbox status methods"""

    def test_get_status(self):
        """Test getting sandbox status"""
        sandbox = Sandbox(
            isolation_level=IsolationLevel.PROCESS,
            workspace_path=Path("/workspace")
        )
        sandbox.register_tools(MockToolRegistry())

        status = sandbox.get_status()

        assert status["isolation_level"] == "process"
        assert "tools_registered" in status
        assert "network_policy" in status
        assert "permissions_count" in status

    def test_cleanup(self):
        """Test sandbox cleanup"""
        sandbox = Sandbox()
        sandbox.cleanup()  # Should not raise


class TestIsolationLevel:
    """Test IsolationLevel enum"""

    def test_isolation_levels_exist(self):
        """Test all isolation levels exist"""
        assert IsolationLevel.PROCESS.value == "process"
        assert IsolationLevel.CONTAINER.value == "container"
        assert IsolationLevel.VM.value == "vm"

    def test_isolation_levels_dict(self):
        """Test ISOLATION_LEVELS dict"""
        assert len(Sandbox.ISOLATION_LEVELS) == 3


class TestPermissionAction:
    """Test PermissionAction enum"""

    def test_permission_actions_exist(self):
        """Test all permission actions exist"""
        assert PermissionAction.ALLOW.value == "allow"
        assert PermissionAction.DENY.value == "deny"
        assert PermissionAction.READONLY.value == "readonly"


class TestOutputTruncation:
    """Test output truncation"""

    def test_truncate_small_output(self):
        """Test truncation of small output"""
        sandbox = Sandbox()

        output = "small output"
        truncated = sandbox._truncate_output(output, "test_tool")

        assert truncated == output

    def test_truncate_large_output(self):
        """Test truncation of large output"""
        sandbox = Sandbox()

        large_output = "x" * 20000
        truncated = sandbox._truncate_output(large_output, "test_tool")

        assert len(truncated) < len(large_output)
        assert "truncated" in truncated

    def test_truncate_with_custom_max_size(self):
        """Test truncation with custom max_output_size"""
        sandbox = Sandbox()
        sandbox.set_permission("test_tool", PermissionAction.ALLOW, max_output_size=100)

        output = "x" * 200
        truncated = sandbox._truncate_output(output, "test_tool")

        assert len(truncated) < 200


class TestExecutionResult:
    """Test ExecutionResult class"""

    def test_execution_result_success(self):
        """Test successful execution result"""
        result = ExecutionResult(
            tool_call_id="call_1",
            content="success result",
            success=True,
            duration_ms=100.0
        )

        assert result.tool_call_id == "call_1"
        assert result.success is True
        assert result.duration_ms == 100.0

    def test_execution_result_to_dict(self):
        """Test ExecutionResult.to_dict"""
        result = ExecutionResult(
            tool_call_id="call_1",
            content="result",
            success=True
        )

        d = result.to_dict()

        assert d["tool_call_id"] == "call_1"
        assert d["role"] == "tool"
        assert d["content"] == "result"


class TestCredentialProxy:
    """Test credential proxy"""

    def test_set_credential_proxy(self):
        """Test setting credential proxy"""
        sandbox = Sandbox()
        proxy = MagicMock()
        proxy.get_credential = MagicMock(return_value="secret")

        sandbox.set_credential_proxy(proxy)

        assert sandbox._credential_proxy == proxy

    def test_get_credential_with_proxy(self):
        """Test getting credential through proxy"""
        sandbox = Sandbox()
        proxy = MagicMock()
        proxy.get_credential = MagicMock(return_value="secret")
        sandbox.set_credential_proxy(proxy)

        cred = sandbox.get_credential("api_key")

        assert cred == "secret"
        proxy.get_credential.assert_called_once_with("api_key")

    def test_get_credential_without_proxy(self):
        """Test getting credential without proxy"""
        sandbox = Sandbox()

        cred = sandbox.get_credential("api_key")

        assert cred is None


class TestPathKeys:
    """Test PATH_KEYS constant"""

    def test_path_keys_defined(self):
        """Test PATH_KEYS is defined"""
        assert len(Sandbox.PATH_KEYS) > 0
        assert "path" in Sandbox.PATH_KEYS
        assert "file_path" in Sandbox.PATH_KEYS