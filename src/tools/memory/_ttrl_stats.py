"""TTRL Win Rate 统计

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning

核心功能：
- Win Rate 分布分析
- 使用频率统计
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def get_win_rate_stats(memory_dir: Path) -> dict[str, object]:
    """获取 Win Rate 统计

    分析已存储记忆的胜率分布。

    Args:
        memory_dir: 记忆目录（L3 knowledge）

    Returns:
        统计结果，包含：
        - total_memories: 总记忆数
        - avg_win_rate: 平均胜率
        - high_win_rate: 高胜率记忆列表 (>= 0.8)
        - low_win_rate: 低胜率记忆列表 (< 0.5)
        - usage_distribution: 使用次数分布
    """
    stats = {
        "total_memories": 0,
        "avg_win_rate": 0.0,
        "high_win_rate": [],  # win_rate >= 0.8
        "low_win_rate": [],  # win_rate < 0.5
        "usage_distribution": {},
    }

    if not memory_dir.exists():
        return stats

    win_rates = []
    usage_counts: dict[int, int] = {}

    for file in memory_dir.glob("*.md"):
        try:
            with open(file, encoding="utf-8") as f:
                content = f.read()

            # 解析 metadata
            if "win_rate=" in content:
                match = re.search(r"win_rate=(\d+\.?\d*)", content)
                if match:
                    win_rate = float(match.group(1))
                    win_rates.append(win_rate)
                    stats["total_memories"] += 1

                    # 分类
                    if win_rate >= 0.8:
                        stats["high_win_rate"].append(file.name)
                    elif win_rate < 0.5:
                        stats["low_win_rate"].append(file.name)

            # 解析 usage_count
            if "usage=" in content:
                match = re.search(r"usage=(\d+)", content)
                if match:
                    usage = int(match.group(1))
                    usage_counts[usage] = usage_counts.get(usage, 0) + 1

        except Exception:
            continue

    if win_rates:
        stats["avg_win_rate"] = sum(win_rates) / len(win_rates)

    stats["usage_distribution"] = usage_counts

    return stats


__all__ = ["get_win_rate_stats"]