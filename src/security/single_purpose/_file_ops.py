"""
文件操作实现

包含文件读写、目录操作、搜索等实现

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容
"""

from src.security.single_purpose._file_read import FileReadOperations
from src.security.single_purpose._file_write import FileWriteOperations


class FileOperations:
    """文件操作实现类"""

    # 读取操作
    read_file = FileReadOperations.read_file
    list_directory = FileReadOperations.list_directory
    find_file = FileReadOperations.find_file
    grep_search = FileReadOperations.grep_search

    # 写入操作
    create_directory = FileWriteOperations.create_directory
    delete_file = FileWriteOperations.delete_file
    delete_directory = FileWriteOperations.delete_directory
    copy_file = FileWriteOperations.copy_file
    move_file = FileWriteOperations.move_file