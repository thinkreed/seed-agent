"""
代码执行实现

包含 Python 脚本执行、测试运行、包安装等实现
"""

import subprocess

from src.security.single_purpose._implementations_types import _get_safe_env


class CodeExecution:
    """代码执行实现类"""

    @staticmethod
    def run_python(args: dict) -> str:
        """执行 Python 脚本（安全：清理环境变量）"""
        script_path = args["script_path"]
        script_args = args.get("args", [])
        timeout = args.get("timeout", 60)

        try:
            cmd = ["python", script_path, *script_args]
            # 安全：清理环境变量，移除敏感凭证
            safe_env = _get_safe_env()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,  # 使用清理后的环境
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

    @staticmethod
    def run_test(args: dict) -> str:
        """执行测试（安全：清理环境变量）"""
        test_path = args["test_path"]
        options = args.get("options", [])
        timeout = args.get("timeout", 120)

        try:
            cmd = ["pytest", test_path, *options]
            # 安全：清理环境变量，移除敏感凭证
            safe_env = _get_safe_env()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,  # 使用清理后的环境
            )

            return result.stdout if result.stdout.strip() else "[OK] Tests passed"

        except subprocess.TimeoutExpired:
            return f"[ERROR] Timeout ({timeout}s)"
        except FileNotFoundError:
            return "[ERROR] pytest not installed"

    @staticmethod
    def install_package(args: dict) -> str:
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
            return f"[ERROR] Install failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "[ERROR] Timeout (60s)"