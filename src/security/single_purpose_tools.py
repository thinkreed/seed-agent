"""
单用途工具工厂 - SinglePurposeToolFactory

将通用 Shell 操作封装为专用工具，提高安全性和可控性

设计原则:
- 单一职责：每个工具只做一件事
- 参数验证：严格验证输入参数
- 风险预设：预定义风险等级
- 安全封装：不暴露通用 Shell

参考来源: Harness Engineering "单用途工具设计"
"""

import fnmatch
import logging
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SinglePurposeToolRisk(str, Enum):
    """单用途工具风险等级"""
    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    DANGEROUS = "dangerous"


@dataclass
class SinglePurposeToolConfig:
    """单用途工具配置"""
    name: str
    description: str
    replaces_command: str  # 替代的通用命令
    risk: SinglePurposeToolRisk
    args_schema: dict[str, Any]  # 参数 schema
    require_confirmation: bool = False
    block_by_default: bool = False
    implementation_func: str | None = None


# 单用途工具定义
SINGLE_PURPOSE_TOOLS: dict[str, SinglePurposeToolConfig] = {
    # === 文件操作 ===
    "read_file_content": SinglePurposeToolConfig(
        name="read_file_content",
        description="读取文件内容（替代 cat）",
        replaces_command="cat <file>",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "path": {"type": "string", "required": True, "description": "文件路径"},
            "encoding": {"type": "string", "required": False, "default": "utf-8"},
            "max_lines": {"type": "integer", "required": False, "default": 1000},
        },
    ),
    "list_directory": SinglePurposeToolConfig(
        name="list_directory",
        description="列出目录内容（替代 ls）",
        replaces_command="ls <dir>",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "path": {"type": "string", "required": True, "description": "目录路径"},
            "recursive": {"type": "boolean", "required": False, "default": False},
            "show_hidden": {"type": "boolean", "required": False, "default": False},
        },
    ),
    "find_file": SinglePurposeToolConfig(
        name="find_file",
        description="查找文件（替代 find）",
        replaces_command="find <dir> -name <pattern>",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "path": {"type": "string", "required": True, "description": "起始目录"},
            "pattern": {"type": "string", "required": True, "description": "文件名模式"},
            "max_depth": {"type": "integer", "required": False, "default": 10},
        },
    ),
    "grep_search": SinglePurposeToolConfig(
        name="grep_search",
        description="搜索文件内容（替代 grep）",
        replaces_command="grep <pattern> <path>",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "pattern": {"type": "string", "required": True, "description": "搜索模式"},
            "path": {"type": "string", "required": True, "description": "搜索路径"},
            "file_pattern": {"type": "string", "required": False, "default": "*"},
        },
    ),
    "create_directory": SinglePurposeToolConfig(
        name="create_directory",
        description="创建目录（替代 mkdir）",
        replaces_command="mkdir <dir>",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "path": {"type": "string", "required": True, "description": "目录路径"},
            "parents": {"type": "boolean", "required": False, "default": True},
        },
    ),
    "delete_file": SinglePurposeToolConfig(
        name="delete_file",
        description="删除文件（替代 rm）",
        replaces_command="rm <file>",
        risk=SinglePurposeToolRisk.RISKY,
        args_schema={
            "path": {"type": "string", "required": True, "description": "文件路径"},
            "force": {"type": "boolean", "required": False, "default": False},
        },
        require_confirmation=True,
    ),
    "delete_directory": SinglePurposeToolConfig(
        name="delete_directory",
        description="删除目录（替代 rmdir）",
        replaces_command="rmdir <dir> / rm -r <dir>",
        risk=SinglePurposeToolRisk.RISKY,
        args_schema={
            "path": {"type": "string", "required": True, "description": "目录路径"},
            "recursive": {"type": "boolean", "required": False, "default": False},
            "force": {"type": "boolean", "required": False, "default": False},
        },
        require_confirmation=True,
    ),
    "copy_file": SinglePurposeToolConfig(
        name="copy_file",
        description="复制文件（替代 cp）",
        replaces_command="cp <src> <dst>",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "src": {"type": "string", "required": True, "description": "源文件"},
            "dst": {"type": "string", "required": True, "description": "目标路径"},
            "overwrite": {"type": "boolean", "required": False, "default": False},
        },
    ),
    "move_file": SinglePurposeToolConfig(
        name="move_file",
        description="移动文件（替代 mv）",
        replaces_command="mv <src> <dst>",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "src": {"type": "string", "required": True, "description": "源文件"},
            "dst": {"type": "string", "required": True, "description": "目标路径"},
            "overwrite": {"type": "boolean", "required": False, "default": False},
        },
    ),

    # === 代码执行 ===
    "run_python_script": SinglePurposeToolConfig(
        name="run_python_script",
        description="执行 Python 脚本",
        replaces_command="python <script.py>",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "script_path": {"type": "string", "required": True, "description": "脚本路径"},
            "args": {"type": "array", "required": False, "default": []},
            "timeout": {"type": "integer", "required": False, "default": 60},
        },
    ),
    "run_test": SinglePurposeToolConfig(
        name="run_test",
        description="执行测试",
        replaces_command="pytest <test_path>",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "test_path": {"type": "string", "required": True, "description": "测试路径"},
            "options": {"type": "array", "required": False, "default": []},
            "timeout": {"type": "integer", "required": False, "default": 120},
        },
    ),
    "install_package": SinglePurposeToolConfig(
        name="install_package",
        description="安装包（替代 pip install）",
        replaces_command="pip install <package>",
        risk=SinglePurposeToolRisk.RISKY,
        args_schema={
            "package": {"type": "string", "required": True, "description": "包名"},
            "version": {"type": "string", "required": False},
            "index": {"type": "string", "required": False, "default": "https://pypi.org/simple"},
        },
        require_confirmation=True,
    ),

    # === Git 操作 ===
    "git_status": SinglePurposeToolConfig(
        name="git_status",
        description="查看 Git 状态",
        replaces_command="git status",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={},
    ),
    "git_diff": SinglePurposeToolConfig(
        name="git_diff",
        description="查看 Git diff",
        replaces_command="git diff",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "file": {"type": "string", "required": False, "description": "文件路径"},
            "staged": {"type": "boolean", "required": False, "default": False},
        },
    ),
    "git_log": SinglePurposeToolConfig(
        name="git_log",
        description="查看 Git 日志",
        replaces_command="git log",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "count": {"type": "integer", "required": False, "default": 10},
            "oneline": {"type": "boolean", "required": False, "default": True},
        },
    ),
    "git_commit": SinglePurposeToolConfig(
        name="git_commit",
        description="Git 提交",
        replaces_command="git commit",
        risk=SinglePurposeToolRisk.RISKY,
        args_schema={
            "message": {"type": "string", "required": True, "description": "提交信息"},
            "amend": {"type": "boolean", "required": False, "default": False},
        },
        require_confirmation=True,
    ),
    "git_push": SinglePurposeToolConfig(
        name="git_push",
        description="Git 推送",
        replaces_command="git push",
        risk=SinglePurposeToolRisk.DANGEROUS,
        args_schema={
            "branch": {"type": "string", "required": False},
            "remote": {"type": "string", "required": False, "default": "origin"},
            "force": {"type": "boolean", "required": False, "default": False},
        },
        require_confirmation=True,
        block_by_default=True,
    ),
    "git_pull": SinglePurposeToolConfig(
        name="git_pull",
        description="Git 拉取",
        replaces_command="git pull",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "branch": {"type": "string", "required": False},
            "remote": {"type": "string", "required": False, "default": "origin"},
        },
    ),
    "git_branch": SinglePurposeToolConfig(
        name="git_branch",
        description="Git 分支操作",
        replaces_command="git branch",
        risk=SinglePurposeToolRisk.CAUTION,
        args_schema={
            "action": {"type": "string", "required": True, "enum": ["list", "create", "delete"]},
            "name": {"type": "string", "required": False},
        },
    ),

    # === 系统信息 ===
    "get_env_info": SinglePurposeToolConfig(
        name="get_env_info",
        description="获取环境信息",
        replaces_command="env / printenv",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "filter": {"type": "string", "required": False},
        },
    ),
    "get_disk_usage": SinglePurposeToolConfig(
        name="get_disk_usage",
        description="获取磁盘使用情况",
        replaces_command="df -h",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={
            "path": {"type": "string", "required": False},
        },
    ),
}


class SinglePurposeToolFactory:
    """单用途工具工厂

    核心功能:
    - 创建单用途工具函数
    - 参数验证
    - 风险预设
    - 安全执行

    Example:
        factory = SinglePurposeToolFactory()
        tool_func = factory.create_tool("read_file_content")
        result = tool_func(path="/tmp/test.txt")
    """

    def __init__(
        self,
        allow_risky_tools: bool = True,
        allow_dangerous_tools: bool = False,
        confirmation_callback: Callable[[str, dict], bool] | None = None,
    ):
        """初始化工具工厂

        Args:
            allow_risky_tools: 是否允许 risky 级别工具
            allow_dangerous_tools: 是否允许 dangerous 级别工具
            confirmation_callback: 用户确认回调函数
        """
        self._allow_risky_tools = allow_risky_tools
        self._allow_dangerous_tools = allow_dangerous_tools
        self._confirmation_callback = confirmation_callback

        logger.info(
            f"SinglePurposeToolFactory initialized: "
            f"allow_risky={allow_risky_tools}, allow_dangerous={allow_dangerous_tools}"
        )

    def create_tool(self, tool_name: str) -> Callable:
        """创建单用途工具

        Args:
            tool_name: 工具名称

        Returns:
            工具函数

        Raises:
            ValueError: 工具不存在或被禁止
        """
        config = SINGLE_PURPOSE_TOOLS.get(tool_name)
        if config is None:
            raise ValueError(f"Unknown single-purpose tool: {tool_name}")

        # 检查工具是否被允许
        if config.block_by_default and not self._allow_dangerous_tools:
            raise ValueError(f"Tool {tool_name} is blocked by default security policy")

        if config.risk == SinglePurposeToolRisk.DANGEROUS and not self._allow_dangerous_tools:
            raise ValueError(f"Tool {tool_name} requires dangerous tool permission")

        if config.risk == SinglePurposeToolRisk.RISKY and not self._allow_risky_tools:
            raise ValueError(f"Tool {tool_name} requires risky tool permission")

        def tool_func(**kwargs) -> str:
            """工具执行函数"""
            # 1. 参数验证
            validated_args = self._validate_args(config, kwargs)

            # 2. 用户确认（如需要）
            if config.require_confirmation:
                confirmed = self._request_confirmation(tool_name, validated_args)
                if not confirmed:
                    return f"[CANCELLED] User cancelled {tool_name}"

            # 3. 执行操作
            try:
                result = self._execute_tool(tool_name, validated_args)
                return result
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                return f"[ERROR] {tool_name} failed: {type(e).__name__}: {str(e)[:200]}"

        # 设置函数属性
        tool_func.__name__ = tool_name
        tool_func.__doc__ = config.description
        tool_func._tool_config = config  # type: ignore

        return tool_func

    def get_tool_config(self, tool_name: str) -> SinglePurposeToolConfig | None:
        """获取工具配置"""
        return SINGLE_PURPOSE_TOOLS.get(tool_name)

    def get_all_tool_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(SINGLE_PURPOSE_TOOLS.keys())

    def get_tools_by_risk(self, risk: SinglePurposeToolRisk) -> list[str]:
        """获取指定风险等级的工具"""
        return [
            name for name, config in SINGLE_PURPOSE_TOOLS.items()
            if config.risk == risk
        ]

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        """获取工具 schema（供 LLM 使用）"""
        config = SINGLE_PURPOSE_TOOLS.get(tool_name)
        if config is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        # 构建 OpenAI function calling 格式的 schema
        properties: dict[str, Any] = {}
        required: list[str] = []

        for arg_name, arg_schema in config.args_schema.items():
            properties[arg_name] = {
                "type": arg_schema.get("type", "string"),
                "description": arg_schema.get("description", ""),
            }
            if arg_schema.get("required"):
                required.append(arg_name)

        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": config.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        """获取所有工具 schema"""
        schemas = []
        for tool_name in self.get_allowed_tool_names():
            try:
                schemas.append(self.get_tool_schema(tool_name))
            except ValueError:
                continue
        return schemas

    def get_allowed_tool_names(self) -> list[str]:
        """获取允许的工具名称"""
        allowed = []

        for name, config in SINGLE_PURPOSE_TOOLS.items():
            # 检查风险等级
            if config.risk == SinglePurposeToolRisk.DANGEROUS:
                if not self._allow_dangerous_tools:
                    continue
            elif config.risk == SinglePurposeToolRisk.RISKY:
                if not self._allow_risky_tools:
                    continue

            # 检查 block_by_default
            if config.block_by_default and not self._allow_dangerous_tools:
                continue

            allowed.append(name)

        return allowed

    def _validate_args(
        self,
        config: SinglePurposeToolConfig,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """验证参数"""
        validated: dict[str, Any] = {}

        for arg_name, arg_schema in config.args_schema.items():
            # 获取参数值
            if arg_name in args:
                value = args[arg_name]
            elif "default" in arg_schema:
                value = arg_schema["default"]
            elif arg_schema.get("required"):
                raise ValueError(f"Missing required argument: {arg_name}")
            else:
                continue

            # 类型检查
            expected_type = arg_schema.get("type", "string")
            if expected_type == "string" and not isinstance(value, str):
                value = str(value)
            elif expected_type == "integer" and not isinstance(value, int):
                try:
                    value = int(value)
                except ValueError:
                    raise ValueError(f"Argument {arg_name} must be integer")
            elif expected_type == "boolean" and not isinstance(value, bool):
                value = str(value).lower() in ("true", "yes", "1")

            # enum 检查
            if "enum" in arg_schema and value not in arg_schema["enum"]:
                raise ValueError(
                    f"Argument {arg_name} must be one of: {arg_schema['enum']}"
                )

            validated[arg_name] = value

        return validated

    def _request_confirmation(self, tool_name: str, args: dict[str, Any]) -> bool:
        """请求用户确认"""
        if self._confirmation_callback:
            return self._confirmation_callback(tool_name, args)

        # 默认行为：记录警告并返回 False（需要外部确认机制）
        logger.warning(f"Tool {tool_name} requires confirmation but no callback set")
        return False

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """执行工具操作

        路由到对应的实现函数
        """
        # 实现函数映射
        implementations: dict[str, Callable] = {
            "read_file_content": self._impl_read_file,
            "list_directory": self._impl_list_directory,
            "find_file": self._impl_find_file,
            "grep_search": self._impl_grep_search,
            "create_directory": self._impl_create_directory,
            "delete_file": self._impl_delete_file,
            "delete_directory": self._impl_delete_directory,
            "copy_file": self._impl_copy_file,
            "move_file": self._impl_move_file,
            "run_python_script": self._impl_run_python,
            "run_test": self._impl_run_test,
            "install_package": self._impl_install_package,
            "git_status": self._impl_git_status,
            "git_diff": self._impl_git_diff,
            "git_log": self._impl_git_log,
            "git_commit": self._impl_git_commit,
            "git_push": self._impl_git_push,
            "git_pull": self._impl_git_pull,
            "git_branch": self._impl_git_branch,
            "get_env_info": self._impl_get_env_info,
            "get_disk_usage": self._impl_get_disk_usage,
        }

        impl_func = implementations.get(tool_name)
        if impl_func is None:
            raise RuntimeError(f"No implementation for tool: {tool_name}")

        return impl_func(args)

    # === 文件操作实现 ===

    def _impl_read_file(self, args: dict[str, Any]) -> str:
        """读取文件"""
        path = args["path"]
        encoding = args.get("encoding", "utf-8")
        max_lines = args.get("max_lines", 1000)

        try:
            with open(path, "r", encoding=encoding) as f:
                lines = f.readlines()

            total_lines = len(lines)
            if total_lines > max_lines:
                lines = lines[:max_lines]

            result = "".join(f"{i + 1}|{line}" for i, line in enumerate(lines))
            result += f"\n--- File: {path}, Lines: 1-{len(lines)}/{total_lines} ---"
            return result

        except FileNotFoundError:
            return f"[ERROR] File not found: {path}"
        except UnicodeDecodeError:
            return f"[ERROR] Cannot decode file with {encoding}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    def _impl_list_directory(self, args: dict[str, Any]) -> str:
        """列出目录"""
        path = args["path"]
        recursive = args.get("recursive", False)
        show_hidden = args.get("show_hidden", False)

        try:
            if recursive:
                lines = []
                for root, dirs, files in os.walk(path):
                    if not show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        files = [f for f in files if not f.startswith(".")]

                    rel_root = os.path.relpath(root, path)
                    lines.append(f"{rel_root}/")
                    for d in dirs:
                        lines.append(f"  {d}/")
                    for f in files:
                        lines.append(f"  {f}")
                return "\n".join(lines)
            else:
                items = os.listdir(path)
                if not show_hidden:
                    items = [i for i in items if not i.startswith(".")]

                lines = []
                for item in sorted(items):
                    full_path = os.path.join(path, item)
                    if os.path.isdir(full_path):
                        lines.append(f"{item}/")
                    else:
                        lines.append(item)
                return "\n".join(lines)

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    def _impl_find_file(self, args: dict[str, Any]) -> str:
        """查找文件"""
        path = args["path"]
        pattern = args["pattern"]
        max_depth = args.get("max_depth", 10)

        try:
            matches = []
            for root, dirs, files in os.walk(path):
                depth = root[len(path):].count(os.sep)
                if depth > max_depth:
                    dirs[:] = []  # 不再深入
                    continue

                for f in files:
                    if pattern in f or f.endswith(pattern):
                        matches.append(os.path.join(root, f))

            if not matches:
                return f"No files matching '{pattern}' found in {path}"

            return "\n".join(matches)

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    def _impl_grep_search(self, args: dict[str, Any]) -> str:
        """搜索文件内容"""
        import re

        pattern = args["pattern"]
        path = args["path"]
        file_pattern = args.get("file_pattern", "*")

        try:
            results = []
            regex = re.compile(pattern, re.IGNORECASE)

            for root, dirs, files in os.walk(path):
                for f in files:
                    if not fnmatch.fnmatch(f, file_pattern):
                        continue

                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, "r", encoding="utf-8") as fp:
                            for i, line in enumerate(fp, 1):
                                if regex.search(line):
                                    results.append(f"{file_path}:{i}:{line.strip()}")
                    except (UnicodeDecodeError, PermissionError):
                        continue

            if not results:
                return f"No matches for '{pattern}' in {path}"

            return "\n".join(results[:100])  # 限制输出

        except FileNotFoundError:
            return f"[ERROR] Path not found: {path}"

    def _impl_create_directory(self, args: dict[str, Any]) -> str:
        """创建目录"""
        import fnmatch  # noqa: F401 (used in grep_search)

        path = args["path"]
        parents = args.get("parents", True)

        try:
            if parents:
                os.makedirs(path, exist_ok=True)
            else:
                os.mkdir(path)

            return f"[OK] Created directory: {path}"

        except FileExistsError:
            return f"[ERROR] Directory already exists: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    def _impl_delete_file(self, args: dict[str, Any]) -> str:
        """删除文件"""
        path = args["path"]

        try:
            os.remove(path)
            return f"[OK] Deleted file: {path}"

        except FileNotFoundError:
            return f"[ERROR] File not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    def _impl_delete_directory(self, args: dict[str, Any]) -> str:
        """删除目录"""
        import shutil

        path = args["path"]
        recursive = args.get("recursive", False)

        try:
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)

            return f"[OK] Deleted directory: {path}"

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except OSError as e:
            if "not empty" in str(e).lower():
                return f"[ERROR] Directory not empty: {path}"
            return f"[ERROR] {e}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    def _impl_copy_file(self, args: dict[str, Any]) -> str:
        """复制文件"""
        import shutil

        src = args["src"]
        dst = args["dst"]
        overwrite = args.get("overwrite", False)

        try:
            if not overwrite and os.path.exists(dst):
                return f"[ERROR] Destination exists: {dst}"

            shutil.copy2(src, dst)
            return f"[OK] Copied {src} → {dst}"

        except FileNotFoundError:
            return f"[ERROR] Source not found: {src}"
        except PermissionError:
            return "[ERROR] Permission denied"

    def _impl_move_file(self, args: dict[str, Any]) -> str:
        """移动文件"""
        import shutil

        src = args["src"]
        dst = args["dst"]
        overwrite = args.get("overwrite", False)

        try:
            if not overwrite and os.path.exists(dst):
                return f"[ERROR] Destination exists: {dst}"

            shutil.move(src, dst)
            return f"[OK] Moved {src} → {dst}"

        except FileNotFoundError:
            return f"[ERROR] Source not found: {src}"
        except PermissionError:
            return "[ERROR] Permission denied"

    # === 代码执行实现 ===

    def _impl_run_python(self, args: dict[str, Any]) -> str:
        """执行 Python 脚本"""
        script_path = args["script_path"]
        script_args = args.get("args", [])
        timeout = args.get("timeout", 60)

        try:
            cmd = ["python", script_path] + script_args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout
            if result.stderr:
                output += "\n[Stderr]\n" + result.stderr
            if result.returncode != 0:
                output += f"\n[Exit Code: {result.returncode}]"

            return output if output.strip() else "[OK] Script executed successfully"

        except subprocess.TimeoutExpired:
            return f"[ERROR] Timeout ({timeout}s)"
        except FileNotFoundError:
            return f"[ERROR] Script not found: {script_path}"

    def _impl_run_test(self, args: dict[str, Any]) -> str:
        """执行测试"""
        test_path = args["test_path"]
        options = args.get("options", [])
        timeout = args.get("timeout", 120)

        try:
            cmd = ["pytest", test_path] + options
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return result.stdout if result.stdout.strip() else "[OK] Tests passed"

        except subprocess.TimeoutExpired:
            return f"[ERROR] Timeout ({timeout}s)"
        except FileNotFoundError:
            return "[ERROR] pytest not installed"

    def _impl_install_package(self, args: dict[str, Any]) -> str:
        """安装包"""
        package = args["package"]
        version = args.get("version")
        index = args.get("index", "https://pypi.org/simple")

        try:
            if version:
                package = f"{package}=={version}"

            cmd = ["pip", "install", package, "--index-url", index]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return f"[OK] Installed: {package}"
            else:
                return f"[ERROR] Install failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "[ERROR] Timeout (60s)"

    # === Git 操作实现 ===

    def _impl_git_status(self, args: dict[str, Any]) -> str:
        """Git status"""
        try:
            result = subprocess.run(
                ["git", "status"],
                capture_output=True,
                text=True,
            )
            return result.stdout if result.stdout.strip() else "[OK] Clean working tree"
        except FileNotFoundError:
            return "[ERROR] git not installed"

    def _impl_git_diff(self, args: dict[str, Any]) -> str:
        """Git diff"""
        file = args.get("file")
        staged = args.get("staged", False)

        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")
            if file:
                cmd.append(file)

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout if result.stdout.strip() else "[OK] No changes"
        except FileNotFoundError:
            return "[ERROR] git not installed"

    def _impl_git_log(self, args: dict[str, Any]) -> str:
        """Git log"""
        count = args.get("count", 10)
        oneline = args.get("oneline", True)

        try:
            cmd = ["git", "log", f"-{count}"]
            if oneline:
                cmd.append("--oneline")

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout
        except FileNotFoundError:
            return "[ERROR] git not installed"

    def _impl_git_commit(self, args: dict[str, Any]) -> str:
        """Git commit"""
        message = args["message"]
        amend = args.get("amend", False)

        try:
            cmd = ["git", "commit", "-m", message]
            if amend:
                cmd.append("--amend")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Committed: {message}"
            else:
                return f"[ERROR] Commit failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    def _impl_git_push(self, args: dict[str, Any]) -> str:
        """Git push"""
        branch = args.get("branch")
        remote = args.get("remote", "origin")
        force = args.get("force", False)

        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            if force:
                cmd.append("--force")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Pushed to {remote}"
            else:
                return f"[ERROR] Push failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    def _impl_git_pull(self, args: dict[str, Any]) -> str:
        """Git pull"""
        branch = args.get("branch")
        remote = args.get("remote", "origin")

        try:
            cmd = ["git", "pull", remote]
            if branch:
                cmd.append(branch)

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return f"[OK] Pulled from {remote}"
            else:
                return f"[ERROR] Pull failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    def _impl_git_branch(self, args: dict[str, Any]) -> str:
        """Git branch"""
        action = args["action"]
        name = args.get("name")

        try:
            cmd = ["git", "branch"]
            if action == "create" and name:
                cmd.append(name)
            elif action == "delete" and name:
                cmd.extend(["-d", name])

            result = subprocess.run(cmd, capture_output=True, text=True)

            if action == "list":
                return result.stdout
            elif result.returncode == 0:
                return f"[OK] Branch {action}: {name}"
            else:
                return f"[ERROR] Branch {action} failed: {result.stderr}"

        except FileNotFoundError:
            return "[ERROR] git not installed"

    # === 系统信息实现 ===

    def _impl_get_env_info(self, args: dict[str, Any]) -> str:
        """获取环境信息"""
        filter_pattern = args.get("filter")

        env_vars = dict(os.environ)
        if filter_pattern:
            env_vars = {
                k: v for k, v in env_vars.items()
                if filter_pattern.lower() in k.lower()
            }

        lines = [f"{k}={v}" for k, v in sorted(env_vars.items())]
        return "\n".join(lines[:50])  # 限制输出

    def _impl_get_disk_usage(self, args: dict[str, Any]) -> str:
        """获取磁盘使用情况"""
        import shutil

        path = args.get("path", "/")
        try:
            total, used, free = shutil.disk_usage(path)
            return (
                f"Total: {total // (1024 ** 3)} GB\n"
                f"Used: {used // (1024 ** 3)} GB\n"
                f"Free: {free // (1024 ** 3)} GB\n"
                f"Usage: {used * 100 // total}%"
            )
        except FileNotFoundError:
            return f"[ERROR] Path not found: {path}"

    def set_confirmation_callback(
        self,
        callback: Callable[[str, dict[str, Any]], bool],
    ) -> None:
        """设置用户确认回调函数"""
        self._confirmation_callback = callback
        logger.info("Confirmation callback set")

    def set_allow_risky_tools(self, allow: bool) -> None:
        """设置是否允许 risky 工具"""
        self._allow_risky_tools = allow
        logger.info(f"Allow risky tools set to: {allow}")

    def set_allow_dangerous_tools(self, allow: bool) -> None:
        """设置是否允许 dangerous 工具"""
        self._allow_dangerous_tools = allow
        logger.info(f"Allow dangerous tools set to: {allow}")