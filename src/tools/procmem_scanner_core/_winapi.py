"""
Memory Scanner Windows API 调用封装
"""

import ctypes
import logging
import sys

from ._types import (
    MEM_COMMIT,
    PAGE_EXECUTE_READ,
    PAGE_EXECUTE_READWRITE,
    PAGE_GUARD,
    PAGE_READONLY,
    PAGE_READWRITE,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_READ,
    USER_SPACE_LIMIT,
    MemoryRegion,
)

logger = logging.getLogger("seed_agent")


def is_admin() -> bool:
    """检查是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        logger.debug(f"is_admin check failed: {type(e).__name__}")
        return False


def open_process(pid: int) -> int | None:
    """打开进程获取句柄"""
    if sys.platform != "win32":
        logger.error("Memory scanning is currently Windows-only.")
        return None

    if not is_admin():
        logger.warning("Administrator privileges required for memory scanning.")

    try:
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if handle == 0:
            logger.error(
                f"Failed to open process {pid}. Error: {ctypes.GetLastError()}"
            )
            return None
        return handle
    except Exception as e:
        logger.exception(f"OpenProcess error: {e}")
        return None


def close_process(handle: int) -> None:
    """关闭进程句柄"""
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)


def read_process_memory(handle: int, address: int, size: int) -> bytes | None:
    """读取进程内存"""
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)

    success = ctypes.windll.kernel32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read)
    )

    if not success:
        return None
    return buffer.raw[: bytes_read.value]


def is_readable_region(protect: int) -> bool:
    """检查内存保护属性是否允许读取"""
    readable_flags = {
        PAGE_READONLY,
        PAGE_READWRITE,
        PAGE_EXECUTE_READ,
        PAGE_EXECUTE_READWRITE,
    }
    return (protect & 0xFF) in readable_flags and not (protect & PAGE_GUARD)


def enumerate_memory_regions(handle: int) -> list[MemoryRegion]:
    """
    枚举进程的所有内存区域

    通过 VirtualQueryEx 遍历整个进程地址空间，
    返回所有已提交 (MEM_COMMIT) 的内存区域。
    """
    regions: list[MemoryRegion] = []
    address = 0

    # MEMORY_BASIC_INFORMATION64 structure
    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", ctypes.c_uint32),
            ("RegionSize", ctypes.c_ulonglong),
            ("State", ctypes.c_uint32),
            ("Protect", ctypes.c_uint32),
            ("Type", ctypes.c_uint32),
        ]

    mbi = MEMORY_BASIC_INFORMATION()

    while True:
        result = ctypes.windll.kernel32.VirtualQueryEx(
            handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)
        )

        if result == 0:
            break

        # 只关注已提交的内存区域
        if mbi.State == MEM_COMMIT:
            regions.append(
                MemoryRegion(
                    base_address=mbi.BaseAddress,
                    region_size=mbi.RegionSize,
                    state=mbi.State,
                    protect=mbi.Protect,
                    type_=mbi.Type,
                )
            )

        address += mbi.RegionSize

        # 安全检查：防止无限循环
        if address >= USER_SPACE_LIMIT:
            break

    return regions