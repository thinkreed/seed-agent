"""超时和自主探索配置

包含 Subagent、RalphLoop 和 Autonomous 相关配置。
"""

from dataclasses import dataclass, field


@dataclass
class SubagentTimeoutConfig:
    """Subagent 超时配置（秒）"""

    explore: int = 180  # EXPLORE: 快速查询 (3m)
    review: int = 600  # REVIEW: 审查+测试 (10m)
    implement: int = 900  # IMPLEMENT: 实现+调试 (15m)
    plan: int = 300  # PLAN: 规划分析 (5m)
    max_iterations: int = 15  # 最大迭代次数


@dataclass
class RalphLoopConfig:
    """Ralph Loop 配置"""

    max_iterations: int = 1000  # 最大迭代次数
    max_duration_hours: int = 8  # 最大执行时间（小时）
    context_reset_interval: int = 50  # 上下文重置间隔（迭代次数）


@dataclass
class AutonomousConfig:
    """自主探索配置（方案 A+C 整合：配置化上限 + 渐进式预算）

    多层防御体系：
    - Layer 1: 预算警告注入（70%/90%阈值）
    - Layer 2: 进度检测窗口（空转循环识别）
    - Layer 3: 时间断路器（单任务时间上限）
    - Layer 4: 递减重试预算（失败重试递减）
    - 安全上限: 1000轮 + 8小时（继承 RalphLoop）
    """

    # === 现有字段 ===
    idle_timeout_hours: int = 2  # 空闲触发时间（小时）
    completion_prompt_tokens: int = 500  # 完成提示 token 数
    max_exploration_rounds: int = 5  # 最大探索轮数

    # 超时保护
    llm_call_timeout_seconds: int = 300  # LLM 单次调用超时（5分钟）
    iteration_timeout_seconds: int = 600  # 单轮迭代总超时（10分钟）

    # Ask User 跳过策略
    ask_user_skip_response: str = "[AUTONOMOUS_SKIP] 自主模式自动跳过用户确认，继续执行"
    ask_user_auto_confirm: bool = True

    # 错误恢复退避
    consecutive_failure_threshold: int = 3
    backoff_duration_seconds: int = 60
    max_backoff_multiplier: int = 5

    # 调试日志
    debug_logging_enabled: bool = True

    # === 方案 A: 配置化上限 ===
    max_iterations_per_task: int = 100  # 单任务迭代上限（可配置）
    max_iterations_high: int = 300  # 高复杂度任务上限
    max_iterations_research: int = 500  # 研究型任务上限
    max_duration_per_task: int = 1800  # 单任务时间上限（秒，30分钟）
    max_retry_count: int = 3  # 最大重试次数

    # === 方案 C: 渐进式预算 ===
    budget_warning_threshold: float = 0.70  # 预算警告阈值（70%）
    budget_urgent_threshold: float = 0.90  # 紧急警告阈值（90%）
    progress_detection_window: int = 5  # 进度检测窗口大小（连续N轮）
    time_warning_threshold: float = 0.80  # 时间警告阈值（80%）
    retry_decay_factors: list[float] = field(
        default_factory=lambda: [1.0, 0.5, 0.25]  # 首次100%, 二次50%, 三次25%
    )
    meaningful_tools: list[str] = field(
        default_factory=lambda: [
            "file_read",
            "file_write",
            "file_edit",
            "code_as_policy",
            "search_grep",
            "search_glob",
        ]
    )


# ========== 全局配置实例 ==========

_subagent_timeout_config = SubagentTimeoutConfig()
_ralph_loop_config = RalphLoopConfig()
_autonomous_config = AutonomousConfig()


def get_subagent_timeout_config() -> SubagentTimeoutConfig:
    """获取 Subagent 超时配置"""
    return _subagent_timeout_config


def get_ralph_loop_config() -> RalphLoopConfig:
    """获取 Ralph Loop 配置"""
    return _ralph_loop_config


def get_autonomous_config() -> AutonomousConfig:
    """获取自主探索配置"""
    return _autonomous_config