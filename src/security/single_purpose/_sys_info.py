"""
系统信息实现

包含环境信息、磁盘使用等实现
"""

import os
import shutil

from src.security.single_purpose._implementations_types import _get_sensitive_env_vars


class SystemInfo:
    """系统信息实现类"""

    @staticmethod
    def get_env_info(args: dict) -> str:
        """获取环境信息（安全：过滤敏感变量）

        安全：不暴露敏感环境变量（API Key、Token、密码等）
        """
        filter_pattern = args.get("filter")
        sensitive_vars = _get_sensitive_env_vars()

        # 获取环境变量并过滤敏感项（使用公共常量）
        env_vars = {}
        for k, v in os.environ.items():
            # 检查是否为敏感变量
            is_sensitive = False
            for sensitive in sensitive_vars:
                if (
                    sensitive.lower() in k.lower()
                    or k.lower().endswith("_key")
                    or k.lower().endswith("_token")
                ):
                    is_sensitive = True
                    break
            if not is_sensitive:
                env_vars[k] = v

        if filter_pattern:
            env_vars = {
                k: v
                for k, v in env_vars.items()
                if filter_pattern.lower() in k.lower()
            }

        lines = [f"{k}={v}" for k, v in sorted(env_vars.items())]
        return "\n".join(lines[:50])  # 限制输出

    @staticmethod
    def get_disk_usage(args: dict) -> str:
        """获取磁盘使用情况"""
        path = args.get("path", "/")
        try:
            total, used, free = shutil.disk_usage(path)
            return (
                f"Total: {total // (1024**3)} GB\n"
                f"Used: {used // (1024**3)} GB\n"
                f"Free: {free // (1024**3)} GB\n"
                f"Usage: {used * 100 // total}%"
            )
        except FileNotFoundError:
            return f"[ERROR] Path not found: {path}"