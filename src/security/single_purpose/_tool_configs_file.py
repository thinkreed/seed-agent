"""文件操作工具配置"""

from ._types import SinglePurposeToolConfig, SinglePurposeToolRisk

# 文件操作工具配置
FILE_OPERATION_TOOLS: dict[str, SinglePurposeToolConfig] = {
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
}

__all__ = ["FILE_OPERATION_TOOLS"]