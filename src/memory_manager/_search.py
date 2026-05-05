"""跨层搜索模块入口

整合 L1-L5 搜索功能
"""

from ._search_l1l3 import search_l1_index, search_l2_skills, search_l3_knowledge
from ._search_l4l5 import search_all_levels, search_l4_user_preferences

__all__ = [
    "search_all_levels",
    "search_l1_index",
    "search_l2_skills",
    "search_l3_knowledge",
    "search_l4_user_preferences",
]