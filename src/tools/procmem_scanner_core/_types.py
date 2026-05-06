"""
Memory Scanner 类型定义
包含数据类和常量定义
"""

from dataclasses import dataclass

# Windows API Constants
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_OPERATION = 0x0008

# Memory Protection Constants
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

# Memory Type Constants
MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
MEM_IMAGE = 0x1000000

# Memory State Constants
MEM_COMMIT = 0x1000

# 64-bit user space limit
USER_SPACE_LIMIT = 0x7FFFFFFFFFFF


@dataclass
class MemoryRegion:
    """内存区域信息"""

    base_address: int
    region_size: int
    state: int
    protect: int
    type_: int