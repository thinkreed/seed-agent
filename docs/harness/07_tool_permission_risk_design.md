# 优化点 07: 工具权限与命令风险分类

> **版本**: v1.0  
> **创建日期**: 2026-05-03  
> **优先级**: 中  
> **依赖**: 02_harness_sandbox_decoupling_design  
> **参考来源**: Harness Engineering "工具与权限"

---

## 问题分析

### Harness Engineering 工具与权限模式

| 模式 | 描述 |
|------|------|
| **渐进式工具扩展** | 开始时只提供最必要工具，复杂工具按需动态加载 |
| **命令风险分类** | 根据命令类型、参数、影响，自动评估风险等级 (安全/有风险/危险) |
| **单用途工具设计** | 常用操作封装为专用工具，而非通用 Shell |

**风险等级定义**:

| 风险等级 | 描述 | 处理策略 |
|----------|------|----------|
| `safe` | 无风险 | 自动执行 |
| `caution` | 轻微风险 | 记录后执行 |
| `risky` | 有风险 | 请求用户确认 |
| `dangerous` | 危险操作 | 直接拦截 |

### seed-agent 当前实现

**已有能力**:

| 能力 | 实现 | 描述 |
|------|------|------|
| SubagentPermissionSets | `subagent.py` | 4种权限集: read_only/review/implement/plan |
| SkillLoader | `skill_loader.py` | 渐进式披露: Index → Content → Reference |
| Skill Security | `skill_security.py` | Prompt注入检测、路径验证 |
| Code Blacklist | `builtin_tools.py` | 30+危险Shell命令黑名单 |

**当前权限集**:

```python
PERMISSION_SETS = {
    "read_only": {"file_read", "search_history", "ask_user"},
    "review":    {"file_read", "code_as_policy", "search_history", "ask_user"},
    "implement": {"file_read", "file_write", "file_edit", "code_as_policy", ...},
    "plan":      {"file_read", "write_memory", "search_history", ...},
}
```

**问题**:
- ❌ 无显式命令风险分类体系
- ❌ 风险评估依赖黑名单，不够智能
- ❌ 无动态工具扩展触发机制
- ❌ 工具权限集固定，无法动态调整
- ⚠️ code_as_policy 使用通用Shell，非单用途设计

---

## 设计方案

### 1. 命令风险分类体系

```python
class CommandRiskClassifier:
    """命令风险分类"""
    
    RISK_LEVELS = {
        "safe": {
            "action": "auto_execute",
            "description": "无风险操作，自动执行",
            "log_level": "INFO",
        },
        "caution": {
            "action": "log_and_execute",
            "description": "轻微风险，记录后执行",
            "log_level": "WARNING",
        },
        "risky": {
            "action": "request_confirm",
            "description": "有风险，请求用户确认",
            "log_level": "WARNING",
            "require_user_approval": True,
        },
        "dangerous": {
            "action": "block",
            "description": "危险操作，直接拦截",
            "log_level": "ERROR",
            "block_message": "此操作被系统安全策略拦截",
        },
    }
    
    # 工具基础风险表
    TOOL_BASE_RISKS = {
        "file_read": "low",
        "file_write": "medium",
        "file_edit": "medium",
        "code_as_policy": "high",
        "ask_user": "low",
        "search_history": "low",
        "write_memory": "medium",
        "spawn_subagent": "medium",
    }
    
    # 参数风险因素
    PARAM_RISK_FACTORS = {
        "path_traversal": {
            "patterns": ["../", "..\\", "~/", "/etc/", "/var/", "/usr/"],
            "risk_boost": 1.0,
        },
        "system_paths": {
            "patterns": ["/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/"],
            "risk_boost": 0.5,
        },
        "overwrite_mode": {
            "conditions": {"mode": "overwrite"},
            "risk_boost": 0.3,
        },
        "shell_language": {
            "conditions": {"language": ["shell", "bash", "sh", "powershell"]},
            "risk_boost": 0.5,
        },
        "dangerous_commands": {
            "patterns": ["rm -rf", "sudo", "chmod 777", "mkfs", "dd if="],
            "risk_boost": 2.0,
        },
    }
    
    def __init__(self, sandbox: Sandbox, user_permission_level: str = "normal"):
        self._sandbox = sandbox
        self._user_permission_level = user_permission_level
        self._classification_history: list[dict] = []
    
    def classify(self, tool_name: str, args: dict) -> tuple[str, str]:
        """分类命令风险
        
        Args:
            tool_name: 工具名称
            args: 工具参数
        
        Returns:
            (risk_level, action): 风险等级和处理策略
        """
        # 1. 工具基础风险
        base_risk = self._get_tool_base_risk(tool_name)
        
        # 2. 参数风险分析
        param_risk = self._analyze_param_risk(tool_name, args)
        
        # 3. 用户权限等级调整
        user_risk_modifier = self._get_user_risk_modifier()
        
        # 4. Sandbox 隔离等级调整
        sandbox_risk_modifier = self._get_sandbox_risk_modifier()
        
        # 5. 综合评估
        final_risk_score = base_risk + param_risk + user_risk_modifier + sandbox_risk_modifier
        
        # 6. 映射到风险等级
        risk_level = self._score_to_level(final_risk_score)
        action = self.RISK_LEVELS[risk_level]["action"]
        
        # 7. 记录分类历史
        self._record_classification(tool_name, args, risk_level, final_risk_score)
        
        return risk_level, action
    
    def _get_tool_base_risk(self, tool_name: str) -> float:
        """获取工具基础风险分数"""
        risk_map = {
            "low": 0.0,
            "medium": 0.5,
            "high": 1.0,
        }
        base_risk = self.TOOL_BASE_RISKS.get(tool_name, "medium")
        return risk_map[base_risk]
    
    def _analyze_param_risk(self, tool_name: str, args: dict) -> float:
        """分析参数风险"""
        risk_score = 0.0
        
        # 1. 检查路径风险因素
        path_args = ["path", "file_path", "directory", "cwd"]
        for path_key in path_args:
            if path_key in args:
                path_value = str(args[path_key])
                
                # 路径遍历检测
                for pattern in self.PARAM_RISK_FACTORS["path_traversal"]["patterns"]:
                    if pattern in path_value:
                        risk_score += self.PARAM_RISK_FACTORS["path_traversal"]["risk_boost"]
                
                # 系统路径检测
                for pattern in self.PARAM_RISK_FACTORS["system_paths"]["patterns"]:
                    if pattern in path_value:
                        risk_score += self.PARAM_RISK_FACTORS["system_paths"]["risk_boost"]
        
        # 2. 检查条件风险因素
        for factor_name, factor_config in self.PARAM_RISK_FACTORS.items():
            if "conditions" in factor_config:
                for condition_key, condition_values in factor_config["conditions"].items():
                    if condition_key in args:
                        if args[condition_key] in condition_values:
                            risk_score += factor_config["risk_boost"]
        
        # 3. 检查代码内容风险 (code_as_policy)
        if tool_name == "code_as_policy" and "code" in args:
            code = str(args["code"])
            
            # 危险命令检测
            for pattern in self.PARAM_RISK_FACTORS["dangerous_commands"]["patterns"]:
                if pattern in code:
                    risk_score += self.PARAM_RISK_FACTORS["dangerous_commands"]["risk_boost"]
        
        return risk_score
    
    def _get_user_risk_modifier(self) -> float:
        """获取用户权限等级风险修正"""
        # 用户权限等级越高，风险修正越低
        modifiers = {
            "admin": -0.5,    # 管理员: 风险降低
            "trusted": -0.3,  # 受信任用户: 风险降低
            "normal": 0.0,    # 正常用户: 不调整
            "guest": 0.3,     # 访客: 风险提高
        }
        return modifiers.get(self._user_permission_level, 0.0)
    
    def _get_sandbox_risk_modifier(self) -> float:
        """获取 Sandbox 隔离等级风险修正"""
        # Sandbox 隔离等级越高，风险修正越低
        modifiers = {
            "vm": -1.0,          # 虚拟机: 风险大幅降低
            "container": -0.5,   # 容器: 风险降低
            "process": -0.3,     # 进程: 风险轻微降低
            "none": 0.0,         # 无隔离: 不调整
        }
        return modifiers.get(self._sandbox.isolation_level, 0.0)
    
    def _score_to_level(self, score: float) -> str:
        """分数映射到风险等级"""
        if score < 0.3:
            return "safe"
        elif score < 0.6:
            return "caution"
        elif score < 1.5:
            return "risky"
        else:
            return "dangerous"
    
    def _record_classification(self, tool_name: str, args: dict, risk_level: str, score: float) -> None:
        """记录分类历史"""
        self._classification_history.append({
            "timestamp": time.time(),
            "tool_name": tool_name,
            "args": args,
            "risk_level": risk_level,
            "score": score,
        })
    
    def get_classification_stats(self) -> dict:
        """获取分类统计"""
        stats = {
            "total_classifications": len(self._classification_history),
            "by_level": {},
        }
        
        for level in ["safe", "caution", "risky", "dangerous"]:
            stats["by_level"][level] = sum(
                1 for c in self._classification_history if c["risk_level"] == level
            )
        
        return stats
```

### 2. 渐进式工具扩展机制

```python
class ProgressiveToolExpander:
    """渐进式工具扩展"""
    
    # 工具层级定义
    TOOL_TIERS = {
        "tier_0_minimal": {
            "description": "最小工具集 - 只读操作",
            "tools": {"file_read", "ask_user", "search_history", "read_memory_index"},
            "trigger": "session_start",
        },
        "tier_1_basic": {
            "description": "基础工具集 - 常用操作",
            "tools": {"file_read", "ask_user", "search_history", "read_memory_index", "search_memory"},
            "trigger": "first_user_request",
        },
        "tier_2_extended": {
            "description": "扩展工具集 - 写入操作",
            "tools": {
                "file_read", "file_write", "file_edit", 
                "ask_user", "search_history", "search_memory",
                "write_memory", "load_skill"
            },
            "trigger": "implementation_task",
        },
        "tier_3_full": {
            "description": "完整工具集 - 高风险操作",
            "tools": {
                "file_read", "file_write", "file_edit",
                "code_as_policy", "ask_user", "search_history",
                "write_memory", "load_skill", "spawn_subagent"
            },
            "trigger": "trusted_user_or_complex_task",
        },
    }
    
    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox
        self._current_tier: str = "tier_0_minimal"
        self._expansion_history: list[dict] = []
    
    def get_available_tools(self, context: dict) -> set[str]:
        """获取当前可用工具集
        
        Args:
            context: 包含 task_type, user_permission, complexity 等
        
        Returns:
            可用工具名称集合
        """
        # 1. 检查是否需要扩展
        new_tier = self._determine_tier(context)
        
        # 2. 如果需要扩展，执行扩展
        if new_tier != self._current_tier:
            self._expand_to_tier(new_tier, context)
        
        # 3. 返回当前层级工具
        return self.TOOL_TIERS[self._current_tier]["tools"]
    
    def _determine_tier(self, context: dict) -> str:
        """确定当前应使用的工具层级"""
        task_type = context.get("task_type", "unknown")
        user_permission = context.get("user_permission", "normal")
        complexity = context.get("complexity", 0.0)
        iteration = context.get("iteration", 0)
        
        # 扩展条件判断
        if user_permission == "admin" or complexity > 0.8:
            return "tier_3_full"
        
        if task_type in ["implementation", "refactoring", "fix"]:
            return "tier_2_extended"
        
        if task_type in ["exploration", "review", "analysis"]:
            return "tier_1_basic"
        
        # 根据迭代次数渐进扩展
        if iteration > 5:
            return "tier_2_extended"
        elif iteration > 0:
            return "tier_1_basic"
        
        return "tier_0_minimal"
    
    def _expand_to_tier(self, new_tier: str, context: dict) -> None:
        """扩展到新层级"""
        old_tier = self._current_tier
        
        # 获取新工具集
        new_tools = self.TOOL_TIERS[new_tier]["tools"]
        old_tools = self.TOOL_TIERS[old_tier]["tools"]
        
        # 计算新增工具
        added_tools = new_tools - old_tools
        
        # 注册新工具到 Sandbox
        for tool_name in added_tools:
            self._sandbox.register_tool(tool_name)
        
        # 更新当前层级
        self._current_tier = new_tier
        
        # 记录扩展历史
        self._expansion_history.append({
            "timestamp": time.time(),
            "from_tier": old_tier,
            "to_tier": new_tier,
            "added_tools": added_tools,
            "context": context,
        })
        
        logger.info(f"Tool tier expanded: {old_tier} → {new_tier}, added {added_tools}")
    
    def expand_for_complex_task(self, complexity_score: float) -> set[str]:
        """复杂任务动态扩展
        
        Args:
            complexity_score: 任务复杂度分数 (0.0 - 1.0)
        
        Returns:
            新增的工具集
        """
        if complexity_score > 0.8:
            # 高复杂度: 扩展到完整工具集
            target_tier = "tier_3_full"
        elif complexity_score > 0.5:
            # 中复杂度: 扩展到扩展工具集
            target_tier = "tier_2_extended"
        else:
            # 低复杂度: 不扩展
            return set()
        
        new_tools = self.TOOL_TIERS[target_tier]["tools"] - self.TOOL_TIERS[self._current_tier]["tools"]
        
        for tool_name in new_tools:
            self._sandbox.register_tool(tool_name)
        
        self._current_tier = target_tier
        return new_tools
    
    def get_expansion_stats(self) -> dict:
        """获取扩展统计"""
        return {
            "current_tier": self._current_tier,
            "total_expansions": len(self._expansion_history),
            "expansion_history": self._expansion_history,
        }
```

### 3. 单用途工具设计

```python
class SinglePurposeToolFactory:
    """单用途工具工厂
    
    将通用 Shell 操作封装为专用工具，提高安全性和可控性
    """
    
    # 单用途工具定义
    SINGLE_PURPOSE_TOOLS = {
        # 文件操作
        "read_file_content": {
            "description": "读取文件内容",
            "replaces": "cat <file>",
            "risk": "safe",
            "args": {"path": "文件路径"},
        },
        "list_directory": {
            "description": "列出目录内容",
            "replaces": "ls <dir>",
            "risk": "safe",
            "args": {"path": "目录路径", "recursive": "是否递归"},
        },
        "find_file": {
            "description": "查找文件",
            "replaces": "find <dir> -name <pattern>",
            "risk": "safe",
            "args": {"path": "起始目录", "pattern": "文件名模式"},
        },
        "create_directory": {
            "description": "创建目录",
            "replaces": "mkdir <dir>",
            "risk": "caution",
            "args": {"path": "目录路径"},
        },
        "delete_file": {
            "description": "删除文件",
            "replaces": "rm <file>",
            "risk": "risky",
            "args": {"path": "文件路径"},
            "require_confirmation": True,
        },
        
        # 代码执行
        "run_python_script": {
            "description": "执行 Python 脚本",
            "replaces": "python <script.py>",
            "risk": "caution",
            "args": {"script_path": "脚本路径", "args": "参数"},
        },
        "run_test": {
            "description": "执行测试",
            "replaces": "pytest <test_path>",
            "risk": "caution",
            "args": {"test_path": "测试路径", "options": "测试选项"},
        },
        "install_package": {
            "description": "安装包",
            "replaces": "pip install <package>",
            "risk": "risky",
            "args": {"package": "包名", "version": "版本"},
            "require_confirmation": True,
        },
        
        # Git 操作
        "git_status": {
            "description": "查看 Git 状态",
            "replaces": "git status",
            "risk": "safe",
            "args": {},
        },
        "git_diff": {
            "description": "查看 Git diff",
            "replaces": "git diff",
            "risk": "safe",
            "args": {"file": "文件路径"},
        },
        "git_commit": {
            "description": "Git 提交",
            "replaces": "git commit",
            "risk": "risky",
            "args": {"message": "提交信息"},
            "require_confirmation": True,
        },
        "git_push": {
            "description": "Git 推送",
            "replaces": "git push",
            "risk": "dangerous",
            "args": {"branch": "分支名"},
            "require_confirmation": True,
            "block_by_default": True,
        },
    }
    
    def create_tool(self, tool_name: str) -> Callable:
        """创建单用途工具
        
        Args:
            tool_name: 工具名称
        
        Returns:
            工具函数
        """
        if tool_name not in self.SINGLE_PURPOSE_TOOLS:
            raise ValueError(f"Unknown single-purpose tool: {tool_name}")
        
        tool_config = self.SINGLE_PURPOSE_TOOLS[tool_name]
        
        def tool_func(**kwargs):
            """工具执行函数"""
            # 1. 参数验证
            validated_args = self._validate_args(tool_name, kwargs)
            
            # 2. 风险检查
            risk_level = tool_config["risk"]
            if risk_level == "dangerous" and tool_config.get("block_by_default"):
                return f"[BLOCKED] 工具 {tool_name} 被默认阻止"
            
            # 3. 用户确认 (如需要)
            if tool_config.get("require_confirmation"):
                confirmed = self._request_user_confirmation(tool_name, validated_args)
                if not confirmed:
                    return f"[CANCELLED] 用户取消 {tool_name}"
            
            # 4. 执行操作
            result = self._execute_single_purpose(tool_name, validated_args)
            
            return result
        
        return tool_func
    
    def _validate_args(self, tool_name: str, args: dict) -> dict:
        """验证参数"""
        tool_config = self.SINGLE_PURPOSE_TOOLS[tool_name]
        expected_args = tool_config["args"]
        
        validated = {}
        for arg_name, arg_value in args.items():
            if arg_name not in expected_args:
                raise ValueError(f"Unexpected arg for {tool_name}: {arg_name}")
            validated[arg_name] = arg_value
        
        return validated
    
    def _execute_single_purpose(self, tool_name: str, args: dict) -> str:
        """执行单用途操作"""
        # 根据工具名称调用对应的实现
        implementations = {
            "read_file_content": lambda a: self._impl_read_file(a["path"]),
            "list_directory": lambda a: self._impl_list_dir(a["path"], a.get("recursive", False)),
            "find_file": lambda a: self._impl_find_file(a["path"], a["pattern"]),
            "create_directory": lambda a: self._impl_create_dir(a["path"]),
            "delete_file": lambda a: self._impl_delete_file(a["path"]),
            "run_python_script": lambda a: self._impl_run_python(a["script_path"], a.get("args")),
            "run_test": lambda a: self._impl_run_test(a["test_path"], a.get("options")),
            "install_package": lambda a: self._impl_install_package(a["package"], a.get("version")),
            "git_status": lambda a: self._impl_git_status(),
            "git_diff": lambda a: self._impl_git_diff(a.get("file")),
            "git_commit": lambda a: self._impl_git_commit(a["message"]),
        }
        
        return implementations[tool_name](args)
    
    # 具体实现 (封装通用 Shell)
    def _impl_read_file(self, path: str) -> str:
        """读取文件"""
        with open(path, "r") as f:
            return f.read()
    
    def _impl_list_dir(self, path: str, recursive: bool) -> str:
        """列出目录"""
        import os
        if recursive:
            return "\n".join(os.walk(path))
        else:
            return "\n".join(os.listdir(path))
    
    # ... 其他实现
```

### 4. 集成到 Sandbox

```python
class SecureSandbox(Sandbox):
    """带风险分类的 Sandbox"""
    
    def __init__(
        self,
        isolation_level: str = "process",
        user_permission_level: str = "normal",
    ):
        super().__init__(isolation_level)
        
        self._risk_classifier = CommandRiskClassifier(self, user_permission_level)
        self._tool_expander = ProgressiveToolExpander(self)
        self._tool_factory = SinglePurposeToolFactory()
    
    async def execute_tool(self, tool_call: dict) -> dict:
        """带风险分类的工具执行"""
        tool_name = tool_call["function"]["name"]
        tool_args = json.loads(tool_call["function"]["arguments"])
        
        # 1. 风险分类
        risk_level, action = self._risk_classifier.classify(tool_name, tool_args)
        
        # 2. 根据风险等级处理
        if action == "block":
            return {
                "tool_call_id": tool_call["id"],
                "error": f"[BLOCKED] 工具 {tool_name} 被安全策略拦截 (风险等级: {risk_level})",
            }
        
        if action == "request_confirm":
            # 请求用户确认
            confirmed = await self._request_user_approval(tool_name, tool_args, risk_level)
            if not confirmed:
                return {
                    "tool_call_id": tool_call["id"],
                    "error": f"[CANCELLED] 用户取消 {tool_name} (风险等级: {risk_level})",
                }
        
        # 3. 记录 (caution 级别)
        if action == "log_and_execute":
            logger.warning(f"Executing cautious tool: {tool_name} with args {tool_args}")
        
        # 4. 执行工具
        result = await super().execute_tool(tool_call)
        
        # 5. 记录执行结果
        self._risk_classifier._record_classification(
            tool_name, tool_args, risk_level, 
            self._risk_classifier._analyze_param_risk(tool_name, tool_args)
        )
        
        return {
            "tool_call_id": tool_call["id"],
            "result": result,
            "risk_level": risk_level,
        }
    
    def get_available_tools(self, context: dict) -> set[str]:
        """获取可用工具 (渐进式扩展)"""
        return self._tool_expander.get_available_tools(context)
    
    def register_single_purpose_tool(self, tool_name: str) -> None:
        """注册单用途工具"""
        tool_func = self._tool_factory.create_tool(tool_name)
        self._tools.register(tool_name, tool_func)
```

---

## 实施步骤

### Phase 1: 命令风险分类 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 1.1 | 实现 CommandRiskClassifier 类 | classify 正确 |
| 1.2 | 实现参数风险分析 | _analyze_param_risk |
| 1.3 | 实现用户/Sandbox 权限修正 | 风险调整正确 |
| 1.4 | 单元测试 | 各种风险等级分类正确 |

### Phase 2: 渐进式工具扩展 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 2.1 | 实现 ProgressiveToolExpander 类 | get_available_tools |
| 2.2 | 实现层级判定 | _determine_tier |
| 2.3 | 实现动态扩展 | expand_for_complex_task |

### Phase 3: 单用途工具设计 (3天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 3.1 | 定义单用途工具集 | SINGLE_PURPOSE_TOOLS |
| 3.2 | 实现工具工厂 | SinglePurposeToolFactory |
| 3.3 | 实现 10+ 单用途工具 | 具体实现函数 |

### Phase 4: Sandbox 集成 (2天)

| 步骤 | 任务 | 验证标准 |
|------|------|----------|
| 4.1 | SecureSandbox 实现 | execute_tool 带风险分类 |
| 4.2 | 集成测试 | 风险分类+扩展+单用途协同 |

---

## 预期收益

| 收益 | 描述 |
|------|------|
| **智能风险评估** | 不依赖黑名单，根据参数动态评估 |
| **渐进式披露** | 工具按需扩展，降低误操作概率 |
| **单用途可控** | 封装通用 Shell，提高安全性 |
| **用户确认机制** | risky/dangerous 操作需确认 |
| **风险统计** | 分类历史追溯 |

---

## 测试计划

```python
def test_risk_classification():
    classifier = CommandRiskClassifier(Sandbox())
    
    # Safe 操作
    level, action = classifier.classify("file_read", {"path": "/tmp/test.txt"})
    assert level == "safe"
    assert action == "auto_execute"
    
    # Risky 操作
    level, action = classifier.classify("file_write", {"path": "/etc/passwd", "mode": "overwrite"})
    assert level == "risky"
    assert action == "request_confirm"
    
    # Dangerous 操作
    level, action = classifier.classify("code_as_policy", {
        "code": "rm -rf /",
        "language": "shell"
    })
    assert level == "dangerous"
    assert action == "block"

def test_progressive_expansion():
    expander = ProgressiveToolExpander(Sandbox())
    
    # 初始层级
    tools = expander.get_available_tools({"iteration": 0})
    assert "code_as_policy" not in tools
    
    # 扩展层级
    tools = expander.get_available_tools({"iteration": 10, "task_type": "implementation"})
    assert "file_write" in tools
    assert "file_edit" in tools
```

---

## 相关文档

- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Sandbox 集成
- [08_credential_security_design.md](08_credential_security_design.md) - 凭证安全