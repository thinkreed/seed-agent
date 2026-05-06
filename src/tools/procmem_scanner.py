"""
Memory Scanner Helper - 进程内存扫描基础模块
支持: Hex/字符串搜索, 特征码定位
注意: 需要管理员权限及 PROCESS_VM_READ 权限

此文件为聚合层，具体实现见 procmem_scanner_core 模块
"""

import logging
import os

from .procmem_scanner_core import (
    MemoryRegion,
    close_process,
    enumerate_memory_regions,
    is_admin,
    is_readable_region,
    open_process,
    read_process_memory,
    scan_memory,
)

logger = logging.getLogger("seed_agent")

# 重新导出公共 API（向后兼容）
__all__ = [
    "MemoryRegion",
    "scan_memory",
    "is_admin",
    "open_process",
    "close_process",
    "read_process_memory",
    "enumerate_memory_regions",
    "is_readable_region",
]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Memory Scanner - Real Implementation")
    logger.info(f"Running as Admin: {is_admin()}")

    if not is_admin():
        logger.warning("Please run as Administrator for full functionality.")

    # 示例：扫描自身进程
    current_pid = os.getpid()
    logger.info(f"Current PID: {current_pid}")

    results = scan_memory(current_pid, "Python", mode="string", max_results=5)
    if results:
        for r in results:
            logger.info(f"  Found at {r['address_hex']} in {r['region_type']} region")
            logger.info(f"  Context: {r['context_hex'][:64]}...")
    else:
        logger.info("  No matches found.")