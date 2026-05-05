"""
文件写入操作实现

包含目录创建、文件删除、目录删除、文件复制、文件移动
"""

import os
import shutil


class FileWriteOperations:
    """文件写入操作实现类"""

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
            return f"[OK] Copied {src} -> {dst}"

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
            return f"[OK] Moved {src} -> {dst}"

        except FileNotFoundError:
            return f"[ERROR] Source not found: {src}"
        except PermissionError:
            return "[ERROR] Permission denied"