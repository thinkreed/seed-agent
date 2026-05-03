# 优化点 07: 工具权限与命令风险分类

> **版本**: v2.0 (已落地实现)
> **创建日期**: 2026-05-03
> **实现日期**: 2026-05-03
> **优先级**: 中
> **状态**: ✅ 已完成
> **依赖**: 02_harness_sandbox_decoupling_design
> **参考来源**: Harness Engineering "工具与权限"

---

## 实现状态

### ✅ 已完成模块

| 模块 | 文件 | 实现状态 |
|------|------|----------|
| **CommandRiskClassifier** | `src/security/risk_classifier.py` | ✅ 已实现 |
| **ProgressiveToolExpander** | `src/security/tool_expander.py` | ✅ 已实现 |
| **SinglePurposeToolFactory** | `src/security/single_purpose_tools.py` | ✅ 已实现 |
| **SecureSandbox** | `src/security/secure_sandbox.py` | ✅ 已实现 |
| **测试** | `tests/test_security.py` | ✅ 已实现 |

### 关键变更

1. **新建 security 模块**: 所有安全相关功能集中在 `src/security/`
2. **完全重写**: 不兼容旧设计，全新的风险分类体系
3. **SecureSandbox 继承 Sandbox**: 无缝集成现有架构
4. **22 个单用途工具**: 文件、代码、Git、系统操作全覆盖

---

## 落地架构

### 模块结构

```
src/security/
├── __init__.py              # 模块入口，导出所有类
├── risk_classifier.py       # CommandRiskClassifier (风险分类)
├── tool_expander.py         # ProgressiveToolExpander (渐进扩展)
├── single_purpose_tools.py  # SinglePurposeToolFactory (单用途工具)
└── secure_sandbox.py        # SecureSandbox (安全沙盒集成)
```

### 类关系图

```
┌─────────────────────────────────────────────────────────────┐
│                    SecureSandbox                             │
│                                                              │
│    继承自 Sandbox                                            │
│    - 集成 RiskClassifier                                    │
│    - 集成 ToolExpander                                      │
│    - 集成 SinglePurposeToolFactory                          │
│                                                              │
│    API:                                                      │
│    - execute_tools_secure()                                 │
│    - classify_tool_risk()                                   │
│    - get_available_tools_secure()                           │
│    - force_expand_to_tier()                                 │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│RiskClassifier │   │ToolExpander   │   │ToolFactory    │
│               │   │               │   │               │
│ classify()    │   │get_available  │   │create_tool()  │
│               │   │_tools()       │   │               │
│ 风险等级:     │   │               │   │ 22 个工具:    │
│ SAFE          │   │ 4 个层级:     │   │ - 文件操作    │
│ CAUTION       │   │ TIER_0        │   │ - Git 操作    │
│ RISKY         │   │ TIER_1        │   │ - 代码执行    │
│ DANGEROUS     │   │ TIER_2        │   │ - 系统信息    │
│               │   │ TIER_3        │   │               │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## 实现细节

### 1. CommandRiskClassifier (风险分类器)

**核心特性**:
- 工具基础风险评估
- 参数风险分析（路径遍历、危险命令、系统路径）
- 用户权限等级修正
- Sandbox 隔离等级修正
- 分类历史追溯

**风险等级配置**:

```python
class RiskLevel(str, Enum):
    SAFE = "safe"        # 自动执行
    CAUTION = "caution"  # 记录后执行
    RISKY = "risky"      # 请求用户确认
    DANGEROUS = "dangerous"  # 直接拦截
```

**工具基础风险表**:

```python
TOOL_BASE_RISKS = {
    # 低风险 (0.0)
    "file_read": 0.0,
    "list_directory": 0.0,
    "git_status": 0.0,
    
    # 中风险 (0.3-0.4)
    "file_write": 0.4,
    "file_edit": 0.4,
    "git_commit": 0.4,
    
    # 高风险 (0.6-0.9)
    "code_as_policy": 0.8,
    "git_push": 0.9,
}
```

**参数风险因素**:

| 因素 | 检测模式 | 风险增量 |
|------|----------|----------|
| path_traversal | `../`, `..\\`, `~/` | +0.8 |
| system_paths | `/etc/`, `/var/`, `C:\\Windows\\` | +0.5 |
| dangerous_commands | `rm -rf`, `sudo`, `mkfs` | +1.5 |
| sensitive_files | `passwd`, `.env`, `credentials` | +0.4 |

**用户权限修正**:

| 权限等级 | 风险修正 |
|----------|----------|
| admin | -0.4 |
| trusted | -0.2 |
| normal | 0.0 |
| guest | +0.3 |
| restricted | +0.5 |

**隔离等级修正**:

| 隔离等级 | 风险修正 |
|----------|----------|
| vm | -0.8 |
| container | -0.5 |
| process | -0.2 |
| none | 0.0 |

### 2. ProgressiveToolExpander (渐进式扩展器)

**工具层级定义**:

| 层级 | 描述 | 工具数量 |
|------|------|----------|
| TIER_0_MINIMAL | 只读操作 | 12 |
| TIER_1_BASIC | 常用操作 | 17 |
| TIER_2_EXTENDED | 写入操作 | 25 |
| TIER_3_FULL | 高风险操作 | 34 |

**层级继承关系**:

```
TIER_0 ⊂ TIER_1 ⊂ TIER_2 ⊂ TIER_3
```

**触发条件**:

| 条件 | 触发层级 |
|------|----------|
| iteration=0 | TIER_0 |
| iteration>0 | TIER_1 |
| task_type=implementation | TIER_2 |
| user_permission=admin | 可达 TIER_3 |
| complexity>0.8 | TIER_3 (需 trusted 用户) |

**用户权限上限**:

| 权限等级 | 层级上限 |
|----------|----------|
| admin/trusted | TIER_3_FULL |
| normal | TIER_2_EXTENDED |
| guest | TIER_1_BASIC |
| restricted | TIER_0_MINIMAL |

### 3. SinglePurposeToolFactory (单用途工具工厂)

**已实现工具** (22个):

| 类别 | 工具 | 风险等级 |
|------|------|----------|
| **文件操作** | read_file_content | SAFE |
| | list_directory | SAFE |
| | find_file | SAFE |
| | grep_search | SAFE |
| | create_directory | CAUTION |
| | delete_file | RISKY (需确认) |
| | delete_directory | RISKY (需确认) |
| | copy_file | CAUTION |
| | move_file | CAUTION |
| **代码执行** | run_python_script | CAUTION |
| | run_test | CAUTION |
| | install_package | RISKY (需确认) |
| **Git 操作** | git_status | SAFE |
| | git_diff | SAFE |
| | git_log | SAFE |
| | git_commit | RISKY (需确认) |
| | git_push | DANGEROUS (默认阻止) |
| | git_pull | CAUTION |
| | git_branch | CAUTION |
| **系统信息** | get_env_info | SAFE |
| | get_disk_usage | SAFE |

**每个工具包含**:
- 参数 schema (类型、必填、默认值)
- 风险等级预设
- 确认需求标记
- 默认阻止标记
- 完整实现函数

### 4. SecureSandbox (安全沙盒)

**继承关系**:

```python
class SecureSandbox(Sandbox):
    """继承自 Sandbox，添加安全特性"""
```

**新增 API**:

| 方法 | 功能 |
|------|------|
| `execute_tools_secure()` | 带风险检查的工具执行 |
| `classify_tool_risk()` | 分类工具风险（不执行） |
| `get_available_tools_secure()` | 获取可用工具（考虑扩展） |
| `force_expand_to_tier()` | 强制扩展工具层级 |
| `get_risk_classification_stats()` | 获取风险分类统计 |
| `get_secure_execution_stats()` | 获取执行统计 |

**执行流程**:

```
execute_tools_secure():
1. 工具可用性检查（渐进式扩展）
2. 风险分类（RiskClassifier）
3. 根据风险等级处理:
   - BLOCK → 直接拦截
   - REQUEST_CONFIRM → 请求用户确认
   - LOG_AND_EXECUTE → 记录后执行
   - AUTO_EXECUTE → 自动执行
4. 优先使用单用途工具
5. 执行标准工具（通过 ToolRegistry）
6. 记录执行历史
```

---

## 测试覆盖

### 测试文件

`tests/test_security.py` 包含:

| 测试类 | 覆盖内容 |
|--------|----------|
| TestCommandRiskClassifier | 风险分类、参数风险、权限修正 |
| TestRiskLevelConfigs | 风险等级配置验证 |
| TestProgressiveToolExpander | 层级判定、动态扩展 |
| TestToolTierConfigs | 层级配置验证 |
| TestSinglePurposeToolFactory | 工具创建、权限控制 |
| TestSinglePurposeToolExecution | 工具执行、确认机制 |
| TestSinglePurposeToolsConfig | 工具配置验证 |
| TestSecureSandbox | 集成测试、状态管理 |
| TestSecureSandboxExecution | 安全执行、阻止/取消 |

### 关键测试场景

```python
# 1. 安全工具自动执行
classifier.classify("file_read", {"path": "/tmp/test.txt"})
# → SAFE, AUTO_EXECUTE

# 2. 危险命令拦截
classifier.classify("code_as_policy", {"code": "rm -rf /"})
# → DANGEROUS, BLOCK

# 3. 路径遍历检测
classifier.classify("file_read", {"path": "/tmp/../etc/passwd"})
# → 风险分数增加

# 4. 渐进式扩展
expander.get_available_tools({"iteration": 0})
# → TIER_0

expander.get_available_tools({"task_type": "implementation"})
# → TIER_2

# 5. 用户权限限制
expander.get_available_tools({"user_permission": "guest"})
# → 限制到 TIER_1

# 6. 单用途工具执行
factory.create_tool("git_status")
# → 创建安全工具函数

factory.create_tool("git_push")
# → ValueError (blocked by default)
```

---

## 性能收益

| 收益 | 描述 |
|------|------|
| **智能风险评估** | 不依赖黑名单，根据参数动态评估 |
| **渐进式披露** | 工具按需扩展，降低误操作概率 |
| **单用途可控** | 封装通用 Shell，提高安全性 |
| **用户确认机制** | risky/dangerous 操作需确认 |
| **风险追溯** | 分类历史可查询 |
| **执行统计** | 完整执行指标 |

---

## 使用示例

### 基础使用

```python
from src.security import SecureSandbox, RiskLevel

# 创建安全沙盒
sandbox = SecureSandbox(
    isolation_level=IsolationLevel.PROCESS,
    user_permission_level="normal"
)

# 注册工具
sandbox.register_tools(tool_registry)

# 获取可用工具
available = sandbox.get_available_tools_secure({
    "task_type": "implementation",
    "iteration": 5
})

# 分类风险（不执行）
result = sandbox.classify_tool_risk("file_write", {
    "path": "/etc/passwd"
})
print(f"Risk: {result.risk_level}, Score: {result.score}")

# 执行工具（带安全检查）
results = await sandbox.execute_tools_secure(tool_calls)
```

### 高级配置

```python
# 管理员配置
sandbox = SecureSandbox(
    user_permission_level="admin",
    allow_dangerous_tools=True,
    enable_single_purpose_tools=True,
    user_confirmation_callback=my_confirm_func
)

# 强制扩展到完整层级
sandbox.force_expand_to_tier(ToolTier.TIER_3_FULL)

# 获取统计
stats = sandbox.get_secure_execution_stats()
print(f"Blocked: {stats['blocked']}")
```

---

## 相关文档

- [02_harness_sandbox_decoupling_design.md](02_harness_sandbox_decoupling_design.md) - Sandbox 集成
- [08_credential_security_design.md](08_credential_security_design.md) - 凭证安全
- [src/security/__init__.py](../src/security/__init__.py) - 模块入口
- [tests/test_security.py](../tests/test_security.py) - 测试文件