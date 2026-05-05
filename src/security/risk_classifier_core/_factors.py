"""
命令风险分类器 - 参数风险因素

包含:
- 参数风险因素配置
- 路径风险检测
- 代码风险检测
"""

from typing import Any

# 参数风险因素
PARAM_RISK_FACTORS: dict[str, dict[str, Any]] = {
    "path_traversal": {
        "patterns": ["../", "..\\", "~/"],
        "risk_boost": 0.8,
        "description": "路径遍历模式",
    },
    "system_paths": {
        "patterns": [
            "/etc/",
            "/var/",
            "/usr/",
            "/bin/",
            "/sbin/",
            "/root/",
            "/home/",
            "/sys/",
            "/proc/",
            "C:\\Windows\\",
            "C:\\Program Files\\",
            "/System/",
            "/Library/",
        ],
        "risk_boost": 0.5,
        "description": "系统路径访问",
    },
    "overwrite_mode": {
        "param_conditions": {"mode": ["overwrite", "w"]},
        "risk_boost": 0.2,
        "description": "覆盖写入模式",
    },
    "shell_language": {
        "param_conditions": {
            "language": ["shell", "bash", "sh", "powershell", "ps", "pwsh"]
        },
        "risk_boost": 0.3,
        "description": "Shell 语言执行",
    },
    "dangerous_commands": {
        "code_patterns": [
            "rm -rf",
            "rm -r",
            "rm -fr",
            "rmdir",
            "del /s",
            "del /q",
            "Remove-Item",
            "Delete-Item",
            "sudo",
            "su",
            "chmod 777",
            "chmod 666",
            "chown",
            "mkfs",
            "dd if=",
            "fdisk",
            "format",
            "shutdown",
            "reboot",
            "wget",
            "curl -o",
            "nc ",
            "netcat",
            "telnet",
            "kill -9",
            "pkill",
            "killall",
            "Stop-Process -Force",
            "> /dev/",
            "mv /*",
            ":(){ :|:& };:",
            "Format-Volume",
            "Stop-Process",
            "Remove-Item -Recurse",
            "eval(",
            "exec(",
            "__import__",
            "import os",
            "import subprocess",
            "os.system",
            "os.popen",
            "subprocess.call",
            "subprocess.run",
            "shell=True",
            "$(",
            "${",
            "`",
            "\\x",
            "\\u",
            "base64",
            "hex",
        ],
        "risk_boost": 1.5,
        "description": "危险命令模式",
    },
    "sensitive_files": {
        "path_patterns": [
            "passwd",
            "shadow",
            "hosts",
            "ssh",
            ".env",
            "credentials",
            "secrets",
            "api_key",
            "private_key",
            "token",
        ],
        "risk_boost": 0.4,
        "description": "敏感文件访问",
    },
    "recursive_flag": {
        "param_conditions": {"recursive": [True, "true", "yes"]},
        "risk_boost": 0.2,
        "description": "递归操作",
    },
    "force_flag": {
        "param_conditions": {"force": [True, "true", "yes", "-f", "--force"]},
        "risk_boost": 0.3,
        "description": "强制执行标志",
    },
}


def check_path_risk(path: str) -> tuple[float, list[str]]:
    """检查路径风险

    Returns:
        (risk_score, factor_descriptions)
    """
    risk_score = 0.0
    factors: list[str] = []

    # 路径遍历检测
    for pattern in PARAM_RISK_FACTORS["path_traversal"]["patterns"]:
        if pattern in path:
            risk_score += PARAM_RISK_FACTORS["path_traversal"]["risk_boost"]
            factors.append(f"path_traversal({pattern})")
            break

    # 系统路径检测
    for pattern in PARAM_RISK_FACTORS["system_paths"]["patterns"]:
        if pattern.lower() in path.lower():
            risk_score += PARAM_RISK_FACTORS["system_paths"]["risk_boost"]
            factors.append(f"system_path({pattern})")
            break

    # 敏感文件检测
    path_lower = path.lower()
    for pattern in PARAM_RISK_FACTORS["sensitive_files"]["path_patterns"]:
        if pattern in path_lower:
            risk_score += PARAM_RISK_FACTORS["sensitive_files"]["risk_boost"]
            factors.append(f"sensitive_file({pattern})")
            break

    return risk_score, factors


def check_code_risk(code: str) -> tuple[float, list[str]]:
    """检查代码风险

    Returns:
        (risk_score, factor_descriptions)
    """
    risk_score = 0.0
    factors: list[str] = []

    code_lower = code.lower()
    dangerous_patterns = PARAM_RISK_FACTORS["dangerous_commands"]["code_patterns"]

    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            risk_score += PARAM_RISK_FACTORS["dangerous_commands"]["risk_boost"]
            factors.append(f"dangerous_command({pattern})")

    return risk_score, factors


def analyze_param_risk(
    tool_name: str,
    args: dict[str, Any],
) -> tuple[float, list[str]]:
    """分析参数风险

    Returns:
        (risk_score, factor_descriptions)
    """
    risk_score = 0.0
    factors: list[str] = []

    # 路径参数检查
    path_keys = ["path", "file_path", "directory", "dir", "cwd", "src", "dst"]
    for key in path_keys:
        if key in args and isinstance(args[key], str):
            path_value = args[key]
            path_risk, path_factors = check_path_risk(path_value)
            risk_score += path_risk
            factors.extend(path_factors)

    # 参数条件检查
    for factor_name, factor_config in PARAM_RISK_FACTORS.items():
        if "param_conditions" in factor_config:
            conditions = factor_config["param_conditions"]
            for param_name, param_values in conditions.items():
                if param_name in args:
                    arg_value = args[param_name]
                    if arg_value in param_values or str(arg_value).lower() in [
                        str(v).lower() for v in param_values
                    ]:
                        risk_score += factor_config["risk_boost"]
                        factors.append(f"{factor_name}({param_name}={arg_value})")

    # 代码内容风险检查
    if tool_name in ("code_as_policy", "run_shell_command"):
        code_keys = ["code", "command", "cmd"]
        for key in code_keys:
            if key in args and isinstance(args[key], str):
                code_risk, code_factors = check_code_risk(args[key])
                risk_score += code_risk
                factors.extend(code_factors)

    return risk_score, factors