"""
builtin_tools.py 单元测试 - 5个核心内置工具测试

覆盖:
- _resolve_path: 路径解析逻辑
- file_read: 文件读取、多编码支持、行范围选择
- file_write: 文件写入、覆盖/追加模式
- file_edit: 文本替换、全部替换
- code_as_policy: 多语言执行、超时处理
- ask_user: 用户交互
- run_diagnosis: 诊断运行
- register_builtin_tools: 工具注册
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from tools.builtin_tools import (  # noqa: E402
    _resolve_path,
    file_read,
    file_write,
    file_edit,
    code_as_policy,
    ask_user,
    run_diagnosis,
    register_builtin_tools,
    DEFAULT_WORK_DIR,
    PROJECT_ROOT,
    _check_code_security,
    _resolve_execution_cwd,
    _build_command,
    _format_execution_result,
    SHELL_BLACKLIST,
    POWERSHELL_BLACKLIST,
)


def _add_test_dir_to_allowed(test_dir: str):
    """临时添加测试目录到允许列表"""
    from src.tools.builtin_tools import ALLOWED_DIRS, _is_path_in_allowed_dirs
    test_path = str(Path(test_dir).resolve())
    if test_path not in ALLOWED_DIRS:
        ALLOWED_DIRS.append(test_path)
    # 清除 lru_cache 以确保新路径被正确检查
    _is_path_in_allowed_dirs.cache_clear()
    return test_path


def _remove_test_dir_from_allowed(test_dir: str):
    """从允许列表移除测试目录"""
    from src.tools.builtin_tools import ALLOWED_DIRS, _is_path_in_allowed_dirs
    test_path = str(Path(test_dir).resolve())
    if test_path in ALLOWED_DIRS:
        ALLOWED_DIRS.remove(test_path)
    # 清除 lru_cache
    _is_path_in_allowed_dirs.cache_clear()


class TestResolvePath(unittest.TestCase):
    """测试 _resolve_path 路径解析逻辑"""

    def test_absolute_path_unchanged(self):
        """绝对路径应保持不变（在允许目录内）"""
        # 使用允许目录内的绝对路径
        abs_path = str(DEFAULT_WORK_DIR / "test_file.txt")
        result = _resolve_path(abs_path)
        # resolve() 可能改变路径格式，比较规范化后的路径
        self.assertEqual(Path(result).resolve(), Path(abs_path).resolve())

    def test_relative_path_seed_exists(self):
        """相对路径 - .seed 中存在文件"""
        with tempfile.NamedTemporaryFile(dir=DEFAULT_WORK_DIR, delete=False, suffix='.txt') as f:
            name = Path(f.name).name
            f.close()  # Windows 上需要先关闭文件句柄
            try:
                result = _resolve_path(name)
                # resolve() 会规范化路径，需要比较规范化后的路径
                self.assertEqual(result, str(Path(f.name).resolve()))
            finally:
                os.unlink(f.name)

    def test_relative_path_fallback_project(self):
        """相对路径 - .seed 不存在，项目根目录存在"""
        with tempfile.NamedTemporaryFile(dir=PROJECT_ROOT, delete=False, suffix='.txt') as f:
            name = Path(f.name).name
            f.close()  # Windows 上需要先关闭文件句柄
            try:
                result = _resolve_path(name)
                # resolve() 会规范化路径，需要比较规范化后的路径
                self.assertEqual(result, str(Path(f.name).resolve()))
            finally:
                os.unlink(f.name)

    def test_relative_path_neither_exists(self):
        """相对路径 - 都不存在，返回 .seed 路径"""
        result = _resolve_path("nonexistent_file.txt")
        self.assertIn(".seed", result)
        self.assertTrue(result.endswith("nonexistent_file.txt"))


class TestFileRead(unittest.TestCase):
    """测试 file_read 文件读取功能"""

    def setUp(self):
        # 使用 DEFAULT_WORK_DIR（已在 ALLOWED_DIRS 中）
        self.test_dir = str(DEFAULT_WORK_DIR)
        self.test_file = os.path.join(self.test_dir, "test_builtin_tools_test.txt")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)
        # 清理所有测试文件（包括 gbk_test.txt 等）
        gbk_file = os.path.join(self.test_dir, "gbk_test.txt")
        if os.path.exists(gbk_file):
            os.unlink(gbk_file)

    def test_read_full_file(self):
        """读取完整文件"""
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("line1\nline2\nline3\n")
        
        result = file_read(self.test_file)
        self.assertIn("1|line1", result)
        self.assertIn("2|line2", result)
        self.assertIn("3|line3", result)

    def test_read_with_line_range(self):
        """按行范围读取"""
        with open(self.test_file, 'w', encoding='utf-8') as f:
            for i in range(1, 11):
                f.write(f"line{i}\n")
        
        result = file_read(self.test_file, start=3, count=3)
        self.assertIn("3|line3", result)
        self.assertIn("4|line4", result)
        self.assertIn("5|line5", result)
        self.assertNotIn("line2", result)
        self.assertNotIn("line6", result)

    def test_file_not_found(self):
        """文件不存在（在允许目录内）"""
        nonexistent_file = os.path.join(self.test_dir, "nonexistent_file.txt")
        result = file_read(nonexistent_file)
        self.assertTrue(result.startswith("Error: File not found"))

    def test_read_empty_range(self):
        """空范围读取"""
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("line1\n")
        
        result = file_read(self.test_file, start=10, count=5)
        self.assertTrue(result.startswith("Empty range"))

    def test_read_gbk_encoded_file(self):
        """读取 GBK 编码文件"""
        gbk_file = os.path.join(self.test_dir, "gbk_test.txt")
        with open(gbk_file, 'w', encoding='gbk') as f:
            f.write("中文测试\n")
        
        result = file_read(gbk_file)
        self.assertIn("中文测试", result)
        self.assertIn("decoded as gbk", result)

    def test_read_file_with_line_numbers(self):
        """输出包含行号"""
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("hello\nworld\n")
        
        result = file_read(self.test_file)
        self.assertIn("1|hello", result)
        self.assertIn("2|world", result)


class TestFileWrite(unittest.TestCase):
    """测试 file_write 文件写入功能"""

    def setUp(self):
        # 使用 DEFAULT_WORK_DIR（已在 ALLOWED_DIRS 中）
        self.test_dir = str(DEFAULT_WORK_DIR)
        self.test_file = os.path.join(self.test_dir, "test_builtin_tools_write.txt")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)
        # 清理可能创建的嵌套目录
        nested_dir = os.path.join(self.test_dir, "a")
        if os.path.exists(nested_dir):
            for root, dirs, files in os.walk(nested_dir, topdown=False):
                for f in files:
                    os.unlink(os.path.join(root, f))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))
            os.rmdir(nested_dir)

    def test_write_overwrite(self):
        """覆盖写入"""
        result = file_write(self.test_file, "hello world")
        self.assertTrue(result.startswith("Successfully written"))
        
        with open(self.test_file, 'r') as f:
            self.assertEqual(f.read(), "hello world")

    def test_write_append(self):
        """追加写入"""
        file_write(self.test_file, "line1\n")
        result = file_write(self.test_file, "line2\n", mode="append")
        self.assertTrue(result.startswith("Successfully appended"))
        
        with open(self.test_file, 'r') as f:
            content = f.read()
            self.assertIn("line1", content)
            self.assertIn("line2", content)

    def test_write_creates_parent_dirs(self):
        """自动创建父目录"""
        nested_file = os.path.join(self.test_dir, "a", "b", "c", "test.txt")
        result = file_write(nested_file, "nested content")
        self.assertTrue(result.startswith("Successfully"))
        self.assertTrue(os.path.exists(nested_file))

    def test_write_relative_path(self):
        """相对路径写入（.seed 目录）"""
        result = file_write("test_relative.txt", "test content")
        self.assertTrue(result.startswith("Successfully"))
        # 清理
        seed_file = DEFAULT_WORK_DIR / "test_relative.txt"
        if seed_file.exists():
            seed_file.unlink()


class TestFileEdit(unittest.TestCase):
    """测试 file_edit 文件编辑功能"""

    def setUp(self):
        # 使用 DEFAULT_WORK_DIR（已在 ALLOWED_DIRS 中）
        self.test_dir = str(DEFAULT_WORK_DIR)
        self.test_file = os.path.join(self.test_dir, "test_builtin_tools_edit.txt")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)

    def test_replace_first_occurrence(self):
        """替换首次出现"""
        with open(self.test_file, 'w') as f:
            f.write("hello world\nhello universe\n")
        
        result = file_edit(self.test_file, "hello", "hi")
        self.assertIn("replaced 1 occurrence", result)
        
        with open(self.test_file, 'r') as f:
            content = f.read()
            self.assertEqual(content, "hi world\nhello universe\n")

    def test_replace_all_occurrences(self):
        """替换所有出现"""
        with open(self.test_file, 'w') as f:
            f.write("hello world\nhello universe\n")
        
        result = file_edit(self.test_file, "hello", "hi", replace_all=True)
        self.assertIn("replaced 2 occurrence", result)
        
        with open(self.test_file, 'r') as f:
            self.assertEqual(f.read(), "hi world\nhi universe\n")

    def test_text_not_found(self):
        """文本未找到"""
        with open(self.test_file, 'w') as f:
            f.write("some content\n")
        
        result = file_edit(self.test_file, "not_found_text", "new_text")
        self.assertTrue(result.startswith("Error: Text not found"))

    def test_file_not_found(self):
        """文件不存在（在允许目录内）"""
        nonexistent_file = os.path.join(self.test_dir, "nonexistent_file.txt")
        result = file_edit(nonexistent_file, "old", "new")
        self.assertTrue(result.startswith("Error: File not found"))


class TestCodeAsPolicy(unittest.TestCase):
    """测试 code_as_policy 代码执行功能"""

    def test_execute_python(self):
        """执行 Python 代码"""
        result = code_as_policy("print('hello from python')", language="python")
        self.assertIn("hello from python", result)

    def test_execute_python_with_error(self):
        """执行 Python 代码（错误）"""
        result = code_as_policy("raise ValueError('test error')", language="python")
        self.assertIn("ValueError", result)
        self.assertIn("test error", result)

    def test_execute_python_timeout(self):
        """执行超时"""
        result = code_as_policy(
            "import time; time.sleep(10)",
            language="python",
            timeout=1
        )
        self.assertIn("timed out", result)

    def test_unsupported_language(self):
        """不支持的语言"""
        result = code_as_policy("print('test')", language="rust")
        self.assertTrue(result.startswith("Error: Unsupported language"))

    def test_default_cwd(self):
        """默认工作目录"""
        result = code_as_policy(
            "import os; print(os.getcwd())",
            language="python"
        )
        self.assertIn(".seed", result)

    def test_exit_code_nonzero(self):
        """非零退出码"""
        result = code_as_policy("import sys; sys.exit(42)", language="python")
        self.assertIn("Exit Code: 42", result)

    def test_clean_output(self):
        """正常执行无错误输出"""
        result = code_as_policy("pass", language="python")
        # 应返回成功消息而非空字符串
        self.assertIn("executed successfully", result.lower())


class TestCodeAsPolicyHelpers(unittest.TestCase):
    """测试 code_as_policy 辅助函数"""

    def test_check_shell_security_clean(self):
        """安全检查通过"""
        result = _check_code_security("echo hello", "shell", None)
        self.assertIsNone(result)

    def test_check_shell_security_blocked(self):
        """安全检查拦截危险命令"""
        result = _check_code_security("rm -rf /", "shell", None)
        self.assertIsNotNone(result)
        self.assertIn("rm -rf", result)

    def test_check_powershell_security_clean(self):
        """PowerShell 安全检查通过"""
        result = _check_code_security("Get-Process", "powershell", None)
        self.assertIsNone(result)

    def test_check_powershell_security_blocked(self):
        """PowerShell 安全检查拦截危险命令"""
        result = _check_code_security("Remove-Item C:\\", "powershell", None)
        self.assertIsNotNone(result)
        self.assertIn("Remove-Item", result)

    def test_resolve_execution_cwd_default(self):
        """默认工作目录为 .seed"""
        result = _resolve_execution_cwd(None)
        self.assertIn(".seed", result)

    def test_resolve_execution_cwd_absolute(self):
        """绝对路径保持不变"""
        result = _resolve_execution_cwd("C:\\temp")
        self.assertEqual(result, "C:\\temp")

    def test_build_command_python(self):
        """构建 Python 命令"""
        cmd = _build_command("print(1)", "python")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd, ["python", "-c", "print(1)"])

    def test_build_command_python_alias(self):
        """构建 Python 命令（别名 py）"""
        cmd = _build_command("print(1)", "py")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd, ["python", "-c", "print(1)"])

    def test_build_command_js_alias(self):
        """构建 JavaScript 命令（别名 js）"""
        cmd = _build_command("console.log(1)", "js")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd, ["node", "-e", "console.log(1)"])

    def test_build_command_unsupported(self):
        """不支持的语言"""
        cmd = _build_command("test", "rust")
        self.assertIsNone(cmd)

    def test_format_execution_result_success(self):
        """格式化成功结果"""
        mock_result = MagicMock(stdout="hello", stderr="", returncode=0)
        result = _format_execution_result(mock_result, "python")
        self.assertEqual(result, "hello")

    def test_format_execution_result_with_stderr(self):
        """格式化含 stderr 的结果"""
        mock_result = MagicMock(stdout="out", stderr="err", returncode=0)
        result = _format_execution_result(mock_result, "python")
        self.assertIn("out", result)
        self.assertIn("err", result)

    def test_format_execution_result_nonzero_exit(self):
        """格式化非零退出码"""
        mock_result = MagicMock(stdout="", stderr="", returncode=42)
        result = _format_execution_result(mock_result, "python")
        self.assertIn("Exit Code: 42", result)

    def test_format_execution_result_empty(self):
        """格式化空输出"""
        mock_result = MagicMock(stdout="", stderr="", returncode=0)
        result = _format_execution_result(mock_result, "python")
        self.assertIn("executed successfully", result.lower())

    def test_shell_blacklist_is_list(self):
        """SHELL_BLACKLIST 是列表"""
        self.assertIsInstance(SHELL_BLACKLIST, list)
        self.assertIn("rm -rf", SHELL_BLACKLIST)

    def test_powershell_blacklist_is_list(self):
        """POWERSHELL_BLACKLIST 是列表"""
        self.assertIsInstance(POWERSHELL_BLACKLIST, list)
        self.assertIn("Remove-Item", POWERSHELL_BLACKLIST)


class TestAskUser(unittest.TestCase):
    """测试 ask_user 用户交互功能"""

    def test_simple_question(self):
        """简单问题"""
        result = ask_user("Are you sure?")
        self.assertIn("[ASK_USER]", result)
        self.assertIn("Are you sure?", result)
        self.assertIn("[Waiting for user response]", result)

    def test_with_options(self):
        """带选项的问题"""
        result = ask_user("Choose:", options=["A", "B", "C"])
        self.assertIn("Options:", result)
        self.assertIn("A", result)
        self.assertIn("B", result)
        self.assertIn("C", result)


class TestRunDiagnosis(unittest.TestCase):
    """测试 run_diagnosis 诊断运行功能"""

    @patch('tools.builtin_tools.Path.exists')
    @patch('tools.builtin_tools.subprocess.run')
    def test_diagnosis_success(self, mock_run, mock_exists):
        """诊断成功"""
        # Mock script exists
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="PASS: 10 checks passed",
            stderr=""
        )

        result = run_diagnosis()
        self.assertIn("PASS", result)

        # 验证调用参数（默认不带 --fix）
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        self.assertNotIn("--fix", str(call_args) if call_args else "")

    @patch('tools.builtin_tools.Path.exists')
    @patch('tools.builtin_tools.subprocess.run')
    def test_diagnosis_with_fix(self, mock_run, mock_exists):
        """带修复参数的诊断"""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="PASS",
            stderr=""
        )
        
        run_diagnosis(fix=True)
        call_args = mock_run.call_args[0][0]
        self.assertIn("--fix", call_args)

    @patch('tools.builtin_tools.Path.exists')
    @patch('tools.builtin_tools.subprocess.run')
    def test_diagnosis_timeout(self, mock_run, mock_exists):
        """诊断超时"""
        import subprocess
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 120)
        
        result = run_diagnosis()
        self.assertIn("timed out", result)


class TestRegisterBuiltinTools(unittest.TestCase):
    """测试 register_builtin_tools 工具注册功能"""

    def test_register_all_tools(self):
        """注册所有工具"""
        mock_registry = MagicMock()
        register_builtin_tools(mock_registry)
        
        expected_tools = [
            "file_read", "file_write", "file_edit",
            "code_as_policy", "ask_user", "run_diagnosis"
        ]
        
        self.assertEqual(mock_registry.register.call_count, len(expected_tools))
        
        # 验证每个工具都被注册
        registered_names = [call[0][0] for call in mock_registry.register.call_args_list]
        for name in expected_tools:
            self.assertIn(name, registered_names)


if __name__ == '__main__':
    unittest.main()
