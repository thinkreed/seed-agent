"""开发工具配置（代码执行、Git操作、系统信息）"""

from ._types import SinglePurposeToolConfig, SinglePurposeToolRisk

# 代码执行工具配置
CODE_EXECUTION_TOOLS: dict[str, SinglePurposeToolConfig] = {
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
}

# Git 操作工具配置
GIT_OPERATION_TOOLS: dict[str, SinglePurposeToolConfig] = {
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
}

# 系统信息工具配置
SYSTEM_INFO_TOOLS: dict[str, SinglePurposeToolConfig] = {
    "get_env_info": SinglePurposeToolConfig(
        name="get_env_info",
        description="获取环境信息",
        replaces_command="env / printenv",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={"filter": {"type": "string", "required": False}},
    ),
    "get_disk_usage": SinglePurposeToolConfig(
        name="get_disk_usage",
        description="获取磁盘使用情况",
        replaces_command="df -h",
        risk=SinglePurposeToolRisk.SAFE,
        args_schema={"path": {"type": "string", "required": False}},
    ),
}

__all__ = ["CODE_EXECUTION_TOOLS", "GIT_OPERATION_TOOLS", "SYSTEM_INFO_TOOLS"]