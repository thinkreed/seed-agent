"""
Memory Scanner Helper - 进程内存扫描基础模块
支持: Hex/字符串搜索, 特征码定位
注意: 需要管理员权限及 PROCESS_VM_READ 权限
"""
import os
import sys
import ctypes
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("seed_agent")

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


@dataclass
class MemoryRegion:
    """内存区域信息"""
    base_address: int
    region_size: int
    state: int
    protect: int
    type_: int


def is_admin() -> bool:
    """检查是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def open_process(pid: int) -> Optional[int]:
    """打开进程获取句柄"""
    if sys.platform != 'win32':
        logger.error("Memory scanning is currently Windows-only.")
        return None
    
    if not is_admin():
        logger.warning("Administrator privileges required for memory scanning.")

    try:
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
            False,
            pid
        )
        if handle == 0:
            logger.error(f"Failed to open process {pid}. Error: {ctypes.GetLastError()}")
            return None
        return handle
    except Exception as e:
        logger.error(f"OpenProcess error: {e}")
        return None


def close_process(handle: int) -> None:
    """关闭进程句柄"""
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)


def read_process_memory(handle: int, address: int, size: int) -> Optional[bytes]:
    """读取进程内存"""
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    
    success = ctypes.windll.kernel32.ReadProcessMemory(
        handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read)
    )
    
    if not success:
        return None
    return buffer.raw[:bytes_read.value]


def enumerate_memory_regions(handle: int) -> List[MemoryRegion]:
    """
    枚举进程的所有内存区域
    
    通过 VirtualQueryEx 遍历整个进程地址空间，
    返回所有已提交 (MEM_COMMIT) 的内存区域。
    """
    regions = []
    address = 0
    mbi = ctypes.c_ulonglong(0)
    mbi_size = ctypes.sizeof(ctypes.c_ulonglong) * 7  # MEMORY_BASIC_INFORMATION64 size
    
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
            handle,
            ctypes.c_void_p(address),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi)
        )
        
        if result == 0:
            break
        
        # 只关注已提交的内存区域
        if mbi.State == 0x1000:  # MEM_COMMIT
            regions.append(MemoryRegion(
                base_address=mbi.BaseAddress,
                region_size=mbi.RegionSize,
                state=mbi.State,
                protect=mbi.Protect,
                type_=mbi.Type
            ))
        
        address += mbi.RegionSize
        
        # 安全检查：防止无限循环
        if address >= 0x7FFFFFFFFFFF:  # 64-bit user space limit
            break
    
    return regions


def is_readable_region(protect: int) -> bool:
    """检查内存保护属性是否允许读取"""
    readable_flags = {
        PAGE_READONLY,
        PAGE_READWRITE,
        PAGE_EXECUTE_READ,
        PAGE_EXECUTE_READWRITE,
    }
    return (protect & 0xFF) in readable_flags and not (protect & PAGE_GUARD)


def _prepare_search_pattern(pattern: str, mode: str) -> Optional[bytes]:
    """Convert pattern string to bytes based on mode."""
    if mode == 'string':
        return pattern.encode('utf-8', errors='ignore')
    elif mode == 'hex':
        try:
            return bytes.fromhex(pattern.replace(' ', ''))
        except ValueError:
            logger.error(f"Invalid hex pattern: {pattern}")
            return None
    logger.error(f"Unknown mode: {mode}")
    return None


def _search_region(data: bytes, pattern: bytes, base_addr: int, max_results: int, results: List[Dict], type_name: str, size: int) -> bool:
    """Search for pattern in data. Returns True if max_results reached."""
    offset = 0
    while len(results) < max_results:
        idx = data.find(pattern, offset)
        if idx == -1:
            return False
        
        addr = base_addr + idx
        ctx_start = max(0, idx - 16)
        ctx_end = min(len(data), idx + len(pattern) + 16)
        
        results.append({
            "address": addr,
            "address_hex": f"0x{addr:016X}",
            "matched": pattern.hex(),
            "context_hex": data[ctx_start:ctx_end].hex(),
            "region_size": size,
            "region_type": type_name
        })
        offset = idx + 1
    return True


def scan_memory(
    pid: int,
    pattern: str,
    mode: str = 'string',
    max_results: int = 10
) -> List[Dict]:
    """
    扫描进程内存
    
    Args:
        pid: 目标进程 ID
        pattern: 搜索模式 (字符串或十六进制)
        mode: 'hex' 或 'string'
        max_results: 最大返回结果数
    """
    if sys.platform != 'win32':
        logger.error("Memory scanning is Windows-only.")
        return []
    
    search_pattern = _prepare_search_pattern(pattern, mode)
    if not search_pattern:
        return []
    
    handle = open_process(pid)
    if not handle:
        return []
    
    try:
        regions = enumerate_memory_regions(handle)
        logger.info(f"Scanning {len(regions)} regions in PID {pid}")
        
        results = []
        for region in regions:
            if not is_readable_region(region.protect) or region.region_size > 100 * 1024 * 1024:
                continue
                
            data = read_process_memory(handle, region.base_address, region.region_size)
            if not data:
                continue
                
            if _search_region(data, search_pattern, region.base_address, max_results, results, 
                             _region_type_name(region.type_), region.region_size):
                break
        
        logger.info(f"Found {len(results)} matches")
        return results
    except Exception as e:
        logger.error(f"Scan error: {e}")
        return []
    finally:
        close_process(handle)


def _region_type_name(type_: int) -> str:
    """获取内存区域类型名称"""
    if type_ == MEM_PRIVATE:
        return "PRIVATE"
    elif type_ == MEM_MAPPED:
        return "MAPPED"
    elif type_ == MEM_IMAGE:
        return "IMAGE"
    return f"UNKNOWN(0x{type_:X})"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Memory Scanner - Real Implementation")
    print(f"Running as Admin: {is_admin()}")
    
    if not is_admin():
        print("Please run as Administrator for full functionality.")
    
    # 示例：扫描自身进程
    current_pid = os.getpid()
    print(f"Current PID: {current_pid}")
    
    results = scan_memory(current_pid, "Python", mode='string', max_results=5)
    if results:
        for r in results:
            print(f"  Found at {r['address_hex']} in {r['region_type']} region")
            print(f"  Context: {r['context_hex'][:64]}...")
    else:
        print("  No matches found.")
