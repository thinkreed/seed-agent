"""
命令风险分类器 - CommandRiskClassifier

根据工具类型、参数内容、用户权限、Sandbox 隔离等级动态评估风险

风险等级:
- SAFE: 无风险，自动执行
- CAUTION: 轻微风险，记录后执行
- RISKY: 有风险，请求用户确认
- DANGEROUS: 危险操作，直接拦截

参考来源: Harness Engineering "工具与权限"
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """风险等级"""
    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    DANGEROUS = "dangerous"


class RiskAction(str, Enum):
    """风险处理策略"""
    AUTO_EXECUTE = "auto_execute"
    LOG_AND_EXECUTE = "log_and_execute"
    REQUEST_CONFIRM = "request_confirm"
    BLOCK = "block"


@dataclass
class RiskLevelConfig:
    """风险等级配置"""
    action: RiskAction
    description: str
    log_level: str
    require_user_approval: bool = False
    block_message: str = ""


# 风险等级配置表
RISK_LEVEL_CONFIGS: dict[RiskLevel, RiskLevelConfig] = {
    RiskLevel.SAFE: RiskLevelConfig(
        action=RiskAction.AUTO_EXECUTE,
        description="无风险操作，自动执行",
        log_level="INFO",
    ),
    RiskLevel.CAUTION: RiskLevelConfig(
        action=RiskAction.LOG_AND_EXECUTE,
        description="轻微风险，记录后执行",
        log_level="WARNING",
    ),
    RiskLevel.RISKY: RiskLevelConfig(
        action=RiskAction.REQUEST_CONFIRM,
        description="有风险，请求用户确认",
        log_level="WARNING",
        require_user_approval=True,
    ),
    RiskLevel.DANGEROUS: RiskLevelConfig(
        action=RiskAction.BLOCK,
        description="危险操作，直接拦截",
        log_level="ERROR",
        block_message="此操作被系统安全策略拦截",
    ),
}


@dataclass
class ClassificationResult:
    """分类结果"""
    risk_level: RiskLevel
    action: RiskAction
    score: float
    tool_name: str
    args: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    factors: list[str] = field(default_factory=list)


class CommandRiskClassifier:
    """命令风险分类器

    核心功能:
    - 工具基础风险评估
    - 参数风险分析（路径遍历、危险命令等）
    - 用户权限等级调整
    - Sandbox 隔离等级调整
    - 分类历史记录

    Example:
        classifier = CommandRiskClassifier(isolation_level="process", user_level="normal")
        result = classifier.classify("file_read", {"path": "/tmp/test.txt"})
        # result.risk_level = RiskLevel.SAFE
        # result.action = RiskAction.AUTO_EXECUTE
    """

    # 工具基础风险表
    TOOL_BASE_RISKS: dict[str, float] = {
        # 低风险工具（只读）
        "file_read": 0.0,
        "list_directory": 0.0,
        "ask_user": 0.0,
        "search_history": 0.0,
        "read_memory_index": 0.0,
        "search_memory": 0.0,
        "load_skill": 0.0,
        "git_status": 0.0,
        "git_diff": 0.0,
        "list_subagents": 0.0,
        "check_ralph_status": 0.0,
        "list_scheduled_tasks": 0.0,

        # 中风险工具（写入/执行）
        "file_write": 0.4,
        "file_edit": 0.4,
        "write_memory": 0.3,
        "create_directory": 0.3,
        "run_python_script": 0.4,
        "run_test": 0.3,
        "git_commit": 0.4,
        "spawn_subagent": 0.4,
        "wait_for_subagent": 0.2,
        "aggregate_subagent_results": 0.2,
        "create_scheduled_task": 0.4,

        # 高风险工具（系统操作）
        "code_as_policy": 0.8,
        "run_shell_command": 0.8,
        "delete_file": 0.7,
        "install_package": 0.6,
        "git_push": 0.9,
        "kill_subagent": 0.5,
        "remove_scheduled_task": 0.5,

        # 默认中等风险
        "default": 0.5,
    }

    # 参数风险因素
    PARAM_RISK_FACTORS: dict[str, dict[str, Any]] = {
        "path_traversal": {
            "patterns": ["../", "..\\", "~/"],
            "risk_boost": 0.8,
            "description": "路径遍历模式",
        },
        "system_paths": {
            "patterns": [
                "/etc/", "/var/", "/usr/", "/bin/", "/sbin/",
                "/root/", "/home/", "/sys/", "/proc/",
                "C:\\Windows\\", "C:\\Program Files\\",
                "/System/", "/Library/",
            ],
            "risk_boost": 0.5,
            "description": "系统路径访问",
        },
        "overwrite_mode": {
            "param_conditions": {"mode": ["overwrite", "w"]},
            "risk_boost": 0.2,
            "description": "覆盖写入模式",
        },
        "shell_language": {
            "param_conditions": {"language": ["shell", "bash", "sh", "powershell", "ps", "pwsh"]},
            "risk_boost": 0.3,
            "description": "Shell 语言执行",
        },
        "dangerous_commands": {
            "code_patterns": [
                "rm -rf", "rm -r", "rmdir", "del /s",
                "sudo", "su", "chmod 777", "chown",
                "mkfs", "dd if=", "fdisk",
                "wget", "curl -o", "nc ", "netcat",
                "kill -9", "pkill", "killall",
                "format", "shutdown", "reboot",
                "> /dev/", "mv /*",
                "Remove-Item", "Delete-Item",
                "Format-Volume", "Stop-Process -Force",
            ],
            "risk_boost": 1.5,
            "description": "危险命令模式",
        },
        "sensitive_files": {
            "path_patterns": [
                "passwd", "shadow", "hosts", "ssh",
                ".env", "credentials", "secrets",
                "api_key", "private_key", "token",
            ],
            "risk_boost": 0.4,
            "description": "敏感文件访问",
        },
        "recursive_flag": {
            "param_conditions": {"recursive": [True, "true", "yes"]},
            "risk_boost": 0.2,
            "description": "递归操作",
        },
        "force_flag": {
            "param_conditions": {"force": [True, "true", "yes", "-f", "--force"]},
            "risk_boost": 0.3,
            "description": "强制执行标志",
        },
    }

    # 用户权限等级修正
    USER_LEVEL_MODIFIERS: dict[str, float] = {
        "admin": -0.4,      # 管理员: 风险降低
        "trusted": -0.2,    # 受信任用户: 风险降低
        "normal": 0.0,      # 正常用户: 不调整
        "guest": 0.3,       # 访客: 风险提高
        "restricted": 0.5,  # 受限用户: 风险大幅提高
    }

    # Sandbox 隔离等级修正
    ISOLATION_LEVEL_MODIFIERS: dict[str, float] = {
        "vm": -0.8,          # 虚拟机: 风险大幅降低
        "container": -0.5,   # 容器: 风险降低
        "process": -0.2,     # 进程: 风险轻微降低
        "none": 0.0,         # 无隔离: 不调整
    }

    def __init__(
        self,
        isolation_level: str = "process",
        user_permission_level: str = "normal",
        max_history_size: int = 1000,
    ):
        """初始化风险分类器

        Args:
            isolation_level: Sandbox 隔离等级 (vm/container/process/none)
            user_permission_level: 用户权限等级 (admin/trusted/normal/guest/restricted)
            max_history_size: 分类历史最大记录数
        """
        self._isolation_level = isolation_level
        self._user_permission_level = user_permission_level
        self._classification_history: list[ClassificationResult] = []
        self._max_history_size = max_history_size

        logger.info(
            f"CommandRiskClassifier initialized: "
            f"isolation={isolation_level}, user_level={user_permission_level}"
        )

    def classify(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> ClassificationResult:
        """分类命令风险

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            ClassificationResult: 分类结果
        """
        factors: list[str] = []

        # 1. 工具基础风险
        base_risk = self._get_tool_base_risk(tool_name)
        if base_risk > 0:
            factors.append(f"tool_base_risk={base_risk:.2f}")

        # 2. 参数风险分析
        param_risk, param_factors = self._analyze_param_risk(tool_name, args)
        factors.extend(param_factors)

        # 3. 用户权限等级调整
        user_modifier = self._get_user_risk_modifier()
        if user_modifier != 0:
            factors.append(f"user_modifier={user_modifier:.2f}")

        # 4. Sandbox 隔离等级调整
        isolation_modifier = self._get_isolation_risk_modifier()
        if isolation_modifier != 0:
            factors.append(f"isolation_modifier={isolation_modifier:.2f}")

        # 5. 综合评估
        final_score = base_risk + param_risk + user_modifier + isolation_modifier
        final_score = max(0.0, final_score)  # 确保分数不为负

        # 6. 映射到风险等级
        risk_level = self._score_to_level(final_score)
        config = RISK_LEVEL_CONFIGS[risk_level]
        action = config.action

        # 7. 创建分类结果
        result = ClassificationResult(
            risk_level=risk_level,
            action=action,
            score=final_score,
            tool_name=tool_name,
            args=args,
            factors=factors,
        )

        # 8. 记录分类历史
        self._record_classification(result)

        # 9. 日志记录
        self._log_classification(result, config)

        return result

    def _get_tool_base_risk(self, tool_name: str) -> float:
        """获取工具基础风险分数"""
        return self.TOOL_BASE_RISKS.get(tool_name, self.TOOL_BASE_RISKS["default"])

    def _analyze_param_risk(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[float, list[str]]:
        """分析参数风险

        Returns:
            (risk_score, factor_descriptions)
        """
        risk_score = 0.0
        factors: list[str] = []

        # 路径参数检查
        path_keys = ["path", "file_path", "directory", "dir", "cwd", "src", "dst"]
        for key in path_keys:
            if key in args and isinstance(args[key], str):
                path_value = args[key]
                path_risk, path_factors = self._check_path_risk(path_value)
                risk_score += path_risk
                factors.extend(path_factors)

        # 参数条件检查
        for factor_name, factor_config in self.PARAM_RISK_FACTORS.items():
            if "param_conditions" in factor_config:
                conditions = factor_config["param_conditions"]
                for param_name, param_values in conditions.items():
                    if param_name in args:
                        arg_value = args[param_name]
                        if arg_value in param_values or str(arg_value).lower() in [str(v).lower() for v in param_values]:
                            risk_score += factor_config["risk_boost"]
                            factors.append(f"{factor_name}({param_name}={arg_value})")

        # 代码内容风险检查 (code_as_policy / run_shell_command)
        if tool_name in ("code_as_policy", "run_shell_command"):
            code_keys = ["code", "command", "cmd"]
            for key in code_keys:
                if key in args and isinstance(args[key], str):
                    code_risk, code_factors = self._check_code_risk(args[key])
                    risk_score += code_risk
                    factors.extend(code_factors)

        return risk_score, factors

    def _check_path_risk(self, path: str) -> tuple[float, list[str]]:
        """检查路径风险"""
        risk_score = 0.0
        factors: list[str] = []

        # 路径遍历检测
        traversal_patterns = self.PARAM_RISK_FACTORS["path_traversal"]["patterns"]
        for pattern in traversal_patterns:
            if pattern in path:
                risk_score += self.PARAM_RISK_FACTORS["path_traversal"]["risk_boost"]
                factors.append(f"path_traversal({pattern})")
                break

        # 系统路径检测
        system_patterns = self.PARAM_RISK_FACTORS["system_paths"]["patterns"]
        for pattern in system_patterns:
            if pattern.lower() in path.lower():
                risk_score += self.PARAM_RISK_FACTORS["system_paths"]["risk_boost"]
                factors.append(f"system_path({pattern})")
                break

        # 敏感文件检测
        sensitive_patterns = self.PARAM_RISK_FACTORS["sensitive_files"]["path_patterns"]
        path_lower = path.lower()
        for pattern in sensitive_patterns:
            if pattern in path_lower:
                risk_score += self.PARAM_RISK_FACTORS["sensitive_files"]["risk_boost"]
                factors.append(f"sensitive_file({pattern})")
                break

        return risk_score, factors

    def _check_code_risk(self, code: str) -> tuple[float, list[str]]:
        """检查代码风险"""
        risk_score = 0.0
        factors: list[str] = []

        code_lower = code.lower()
        dangerous_patterns = self.PARAM_RISK_FACTORS["dangerous_commands"]["code_patterns"]

        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                risk_score += self.PARAM_RISK_FACTORS["dangerous_commands"]["risk_boost"]
                factors.append(f"dangerous_command({pattern})")

        return risk_score, factors

    def _get_user_risk_modifier(self) -> float:
        """获取用户权限等级风险修正"""
        return self.USER_LEVEL_MODIFIERS.get(self._user_permission_level, 0.0)

    def _get_isolation_risk_modifier(self) -> float:
        """获取 Sandbox 隔离等级风险修正"""
        return self.ISOLATION_LEVEL_MODIFIERS.get(self._isolation_level, 0.0)

    def _score_to_level(self, score: float) -> RiskLevel:
        """分数映射到风险等级"""
        if score < 0.3:
            return RiskLevel.SAFE
        if score < 0.6:
            return RiskLevel.CAUTION
        if score < 1.2:
            return RiskLevel.RISKY
        return RiskLevel.DANGEROUS

    def _record_classification(self, result: ClassificationResult) -> None:
        """记录分类历史"""
        self._classification_history.append(result)

        # 限制历史大小
        if len(self._classification_history) > self._max_history_size:
            self._classification_history = self._classification_history[-self._max_history_size:]

    def _log_classification(
        self,
        result: ClassificationResult,
        config: RiskLevelConfig,
    ) -> None:
        """日志记录分类结果"""
        log_msg = (
            f"Risk classification: tool={result.tool_name}, "
            f"level={result.risk_level.value}, "
            f"score={result.score:.2f}, "
            f"action={result.action.value}, "
            f"factors=[{', '.join(result.factors)}]"
        )

        if config.log_level == "INFO":
            logger.info(log_msg)
        elif config.log_level == "WARNING":
            logger.warning(log_msg)
        elif config.log_level == "ERROR":
            logger.error(log_msg)

    def get_classification_stats(self) -> dict[str, Any]:
        """获取分类统计"""
        stats: dict[str, Any] = {
            "total_classifications": len(self._classification_history),
            "by_level": {},
            "by_action": {},
            "average_score": 0.0,
        }

        # 按等级统计
        for level in RiskLevel:
            stats["by_level"][level.value] = sum(
                1 for c in self._classification_history if c.risk_level == level
            )

        # 按动作统计
        for action in RiskAction:
            stats["by_action"][action.value] = sum(
                1 for c in self._classification_history if c.action == action
            )

        # 平均分数
        if self._classification_history:
            stats["average_score"] = sum(
                c.score for c in self._classification_history
            ) / len(self._classification_history)

        return stats

    def get_recent_classifications(self, limit: int = 10) -> list[ClassificationResult]:
        """获取最近的分类记录"""
        return self._classification_history[-limit:]

    def clear_history(self) -> None:
        """清空分类历史"""
        self._classification_history.clear()
        logger.info("Classification history cleared")

    def update_user_level(self, new_level: str) -> None:
        """更新用户权限等级"""
        self._user_permission_level = new_level
        logger.info(f"User permission level updated: {new_level}")

    def update_isolation_level(self, new_level: str) -> None:
        """更新隔离等级"""
        self._isolation_level = new_level
        logger.info(f"Isolation level updated: {new_level}")
