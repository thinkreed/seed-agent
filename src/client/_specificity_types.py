"""
Specificity 类型定义

包含枚举、dataclass 和配置常量。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpecificityType(Enum):
    """任务特定类型"""
    CODING = "coding"            # 代码编写
    DATA_ANALYSIS = "data_analysis"  # 数据分析
    WEB_BROWSING = "web_browsing"    # 网页浏览
    PLANNING = "planning"        # 规划设计
    REASONING = "reasoning"      # 推理分析
    CONVERSATION = "conversation"    # 对话问答
    GENERAL = "general"          # 通用任务


@dataclass
class SpecificityResult:
    """Specificity 检测结果"""
    detected_type: SpecificityType
    confidence: float
    keywords_matched: list[str] = field(default_factory=list)
    patterns_matched: list[str] = field(default_factory=list)
    model_override: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# 特定类型关键词配置
SPECIFICITY_KEYWORDS: dict[SpecificityType, list[str]] = {
    SpecificityType.CODING: [
        "代码", "函数", "类", "模块", "重构", "调试", "bug",
        "code", "function", "class", "module", "refactor", "debug",
        "implement", "python", "javascript", "typescript", "java", "go",
        "写代码", "修改", "实现", "添加", "删除", "创建",
        "文件", "编辑", "git", "commit", "test", "测试",
    ],
    SpecificityType.DATA_ANALYSIS: [
        "数据", "分析", "统计", "可视化", "图表", "报表",
        "data", "analysis", "statistics", "visualization", "chart",
        "csv", "json", "excel", "pandas", "numpy", "plot",
        "计算", "平均值", "分布", "趋势", "预测",
    ],
    SpecificityType.WEB_BROWSING: [
        "网页", "浏览", "搜索", "网站", "链接", "内容",
        "web", "browse", "search", "website", "link", "content",
        "url", "http", "fetch", "download", "爬取", "抓取",
        "查看", "访问", "获取", "读取网页",
    ],
    SpecificityType.PLANNING: [
        "规划", "计划", "设计", "方案", "架构", "策略",
        "plan", "design", "scheme", "architecture", "strategy",
        "步骤", "流程", "路线", "里程碑", "时间表",
        "如何", "怎么做", "实现方案", "设计方案",
    ],
    SpecificityType.REASONING: [
        "推理", "分析", "判断", "决策", "比较", "评估",
        "reason", "analyze", "judge", "decide", "compare", "evaluate",
        "为什么", "原因", "影响", "后果", "可能性",
        "思考", "考虑", "权衡", "选择", "取舍",
    ],
    SpecificityType.CONVERSATION: [
        "解释", "说明", "介绍", "什么是", "如何理解",
        "explain", "describe", "introduce", "what is", "how to",
        "帮我", "请", "可以", "能否", "帮我理解",
        "问题", "疑问", "困惑", "请教",
    ],
}

# 特定类型模型映射
SPECIFICITY_MODEL_MAPPING: dict[SpecificityType, str] = {
    SpecificityType.CODING: "claude-3-5-sonnet",
    SpecificityType.DATA_ANALYSIS: "gpt-4o",
    SpecificityType.WEB_BROWSING: "gpt-4o-mini",
    SpecificityType.PLANNING: "claude-3-5-sonnet",
    SpecificityType.REASONING: "claude-3-opus",
    SpecificityType.CONVERSATION: "gpt-4o-mini",
    SpecificityType.GENERAL: "gpt-4o",
}

# 特定类型正则模式
SPECIFICITY_PATTERNS: dict[SpecificityType, list[str]] = {
    SpecificityType.CODING: [
        r'(write|create|implement|modify|edit|fix)\s+(a|the|this)?\s*(function|class|module|script|code)',
        r'(def |function |class |import |from |async def)',
        r'(\.py|\.js|\.ts|\.java|\.go|\.rs)',
        r'(git|commit|push|pull|merge|branch)',
        r'(syntax|error|bug|fix|debug)',
    ],
    SpecificityType.DATA_ANALYSIS: [
        r'(analyze|analysis)\s+(the|this)?\s*(data|dataset|file)',
        r'(csv|json|excel|pandas|numpy)',
        r'(plot|chart|graph|visualize)',
        r'(statistics|average|mean|median|std)',
    ],
    SpecificityType.WEB_BROWSING: [
        r'(browse|visit|fetch|download|scrape)\s+(the|this)?\s*(url|website|page|link)',
        r'(https?://|www\.)',
        r'(web|internet|online)',
    ],
    SpecificityType.PLANNING: [
        r'(plan|design|create)\s+(a|the)?\s*(plan|scheme|architecture|strategy)',
        r'(step|phase|milestone|timeline)',
        r'(roadmap|approach|method)',
    ],
    SpecificityType.REASONING: [
        r'(analyze|analyze|reason|judge|decide)\s+(the|this)?',
        r'(why|reason|cause|impact|effect)',
        r'(compare|evaluate|assess)',
    ],
    SpecificityType.CONVERSATION: [
        r'(explain|describe|introduce)\s+(what|how|why)',
        r'(help\s+me|please\s+help|can\s+you)',
        r'(what\s+is|how\s+to|tell\s+me)',
    ],
}