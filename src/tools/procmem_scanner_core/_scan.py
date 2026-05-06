"""
Memory Scanner 扫描逻辑
"""

import logging
import sys
from typing import Any

from ._types import MEM_IMAGE, MEM_MAPPED, MEM_PRIVATE
from ._winapi import (
    close_process,
    enumerate_memory_regions,
    is_readable_region,
    open_process,
    read_process_memory,
)

logger = logging.getLogger("seed_agent")


def _prepare_search_pattern(pattern: str, mode: str) -> bytes | None:
    """Convert pattern string to bytes based on mode."""
    if mode == "string":
        return pattern.encode("utf-8", errors="ignore")
    if mode == "hex":
        try:
            return bytes.fromhex(pattern.replace(" ", ""))
        except ValueError:
            logger.exception(f"Invalid hex pattern: {pattern}")
            return None
    logger.error(f"Unknown mode: {mode}")
    return None


def _region_type_name(type_: int) -> str:
    """获取内存区域类型名称"""
    if type_ == MEM_PRIVATE:
        return "PRIVATE"
    if type_ == MEM_MAPPED:
        return "MAPPED"
    if type_ == MEM_IMAGE:
        return "IMAGE"
    return f"UNKNOWN(0x{type_:X})"


def _search_region(
    data: bytes,
    pattern: bytes,
    base_addr: int,
    max_results: int,
    results: list[dict[str, Any]],
    type_name: str,
    size: int,
) -> bool:
    """Search for pattern in data. Returns True if max_results reached."""
    offset = 0
    while len(results) < max_results:
        idx = data.find(pattern, offset)
        if idx == -1:
            return False

        addr = base_addr + idx
        ctx_start = max(0, idx - 16)
        ctx_end = min(len(data), idx + len(pattern) + 16)

        results.append(
            {
                "address": addr,
                "address_hex": f"0x{addr:016X}",
                "matched": pattern.hex(),
                "context_hex": data[ctx_start:ctx_end].hex(),
                "region_size": size,
                "region_type": type_name,
            }
        )
        offset = idx + 1
    return True


def scan_memory(
    pid: int, pattern: str, mode: str = "string", max_results: int = 10
) -> list[dict[str, Any]]:
    """
    扫描进程内存

    Args:
        pid: 目标进程 ID
        pattern: 搜索模式 (字符串或十六进制)
        mode: 'hex' 或 'string'
        max_results: 最大返回结果数
    """
    if sys.platform != "win32":
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

        results: list[dict[str, Any]] = []
        for region in regions:
            if (
                not is_readable_region(region.protect)
                or region.region_size > 100 * 1024 * 1024
            ):
                continue

            data = read_process_memory(handle, region.base_address, region.region_size)
            if not data:
                continue

            if _search_region(
                data,
                search_pattern,
                region.base_address,
                max_results,
                results,
                _region_type_name(region.type_),
                region.region_size,
            ):
                break

        logger.info(f"Found {len(results)} matches")
        return results
    except Exception as e:
        logger.exception(f"Scan error: {e}")
        return []
    finally:
        close_process(handle)