"""
单用途工具配置定义

包含:
- SinglePurposeToolRisk: 风险等级枚举
- SinglePurposeToolConfig: 工具配置数据类
- SINGLE_PURPOSE_TOOLS: 工具定义字典
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SinglePurposeToolRisk(StrEnum):
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
            "pattern": {
                "type": "string",
                "required": True,
                "description": "文件名模式",
            },
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
            "script_path": {
                "type": "string",
                "required": True,
                "description": "脚本路径",
            },
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
            "test_path": {
                "type": "string",
                "required": True,
                "description": "测试路径",
            },
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
            "index": {
                "type": "string",
                "required": False,
                "default": "https://pypi.org/simple",
            },
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
            "action": {
                "type": "string",
                "required": True,
                "enum": ["list", "create", "delete"],
            },
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