"""
Memory Scanner Core - 进程内存扫描核心模块

导出公共 API:
- MemoryRegion: 内存区域数据类
- scan_memory: 扫描进程内存
- is_admin: 检查管理员权限
- open_process: 打开进程句柄
- close_process: 关闭进程句柄
- read_process_memory: 读取进程内存
- enumerate_memory_regions: 枚举内存区域
- is_readable_region: 检查区域可读性
"""

from ._scan import scan_memory
from ._types import (
    MEM_COMMIT,
    MEM_IMAGE,
    MEM_MAPPED,
    MEM_PRIVATE,
    PAGE_EXECUTE_READ,
    PAGE_EXECUTE_READWRITE,
    PAGE_GUARD,
    PAGE_NOACCESS,
    PAGE_READONLY,
    PAGE_READWRITE,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_OPERATION,
    PROCESS_VM_READ,
    USER_SPACE_LIMIT,
    MemoryRegion,
)
from ._winapi import (
    close_process,
    enumerate_memory_regions,
    is_admin,
    is_readable_region,
    open_process,
    read_process_memory,
)

__all__ = [
    # 数据类
    "MemoryRegion",
    # 核心功能
    "scan_memory",
    # Windows API 封装
    "is_admin",
    "open_process",
    "close_process",
    "read_process_memory",
    "enumerate_memory_regions",
    "is_readable_region",
    # 常量
    "PROCESS_QUERY_INFORMATION",
    "PROCESS_VM_READ",
    "PROCESS_VM_OPERATION",
    "PAGE_READWRITE",
    "PAGE_READONLY",
    "PAGE_EXECUTE_READ",
    "PAGE_EXECUTE_READWRITE",
    "PAGE_GUARD",
    "PAGE_NOACCESS",
    "MEM_PRIVATE",
    "MEM_MAPPED",
    "MEM_IMAGE",
    "MEM_COMMIT",
    "USER_SPACE_LIMIT",
]