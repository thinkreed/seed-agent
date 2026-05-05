"""
文件操作实现

包含文件读写、目录操作、搜索等实现
"""

import fnmatch
import os
import re
import shutil


class FileOperations:
    """文件操作实现类"""

    @staticmethod
    def read_file(args: dict) -> str:
        """读取文件"""
        path = args["path"]
        encoding = args.get("encoding", "utf-8")
        max_lines = args.get("max_lines", 1000)

        try:
            with open(path, encoding=encoding) as f:
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

    @staticmethod
    def list_directory(args: dict) -> str:
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
                    lines.extend(f"  {d}/" for d in dirs)
                    lines.extend(f"  {f}" for f in files)
                return "\n".join(lines)

            items = os.listdir(path)
            if not show_hidden:
                items = [i for i in items if not i.startswith(".")]

            lines = [
                f"{item}/" if os.path.isdir(os.path.join(path, item)) else item
                for item in sorted(items)
            ]
            return "\n".join(lines)

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def find_file(args: dict) -> str:
        """查找文件"""
        path = args["path"]
        pattern = args["pattern"]
        max_depth = args.get("max_depth", 10)

        try:
            matches: list[str] = []
            for root, dirs, files in os.walk(path):
                depth = root[len(path) :].count(os.sep)
                if depth > max_depth:
                    dirs[:] = []  # 不再深入
                    continue

                matches.extend(
                    os.path.join(root, f)
                    for f in files
                    if pattern in f or f.endswith(pattern)
                )

            if not matches:
                return f"No files matching '{pattern}' found in {path}"

            return "\n".join(matches)

        except FileNotFoundError:
            return f"[ERROR] Directory not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def grep_search(args: dict) -> str:
        """搜索文件内容"""
        pattern = args["pattern"]
        path = args["path"]
        file_pattern = args.get("file_pattern", "*")

        try:
            results = []
            regex = re.compile(pattern, re.IGNORECASE)

            for root, _, files in os.walk(path):
                for f in files:
                    if not fnmatch.fnmatch(f, file_pattern):
                        continue

                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, encoding="utf-8") as fp:
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

    @staticmethod
    def create_directory(args: dict) -> str:
        """创建目录"""
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

    @staticmethod
    def delete_file(args: dict) -> str:
        """删除文件"""
        path = args["path"]

        try:
            os.remove(path)
            return f"[OK] Deleted file: {path}"

        except FileNotFoundError:
            return f"[ERROR] File not found: {path}"
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

    @staticmethod
    def delete_directory(args: dict) -> str:
        """删除目录"""
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

    @staticmethod
    def copy_file(args: dict) -> str:
        """复制文件"""
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

    @staticmethod
    def move_file(args: dict) -> str:
        """移动文件"""
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