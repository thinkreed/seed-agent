# AutonomousExplorer 循环限制放宽设计

> **版本**: v2.0 (已实施)
> **创建日期**: 2026-05-04
> **实施日期**: 2026-05-04
> **优先级**: 中
> **依赖**: long_cycle_loop_enhancement_design.md, ralph_loop.md
> **状态**: ✅ 已实施（方案 A+C 组合落地完成）
> **参考来源**: Harness Engineering "确定性生命周期钩子体系"

---

## 实施概要

### 已落地改动

| 文件 | 改动 |
|------|------|
| `src/shared_config.py` | 新增 `AutonomousConfig` 字段（方案 A+C 配置） |
| `src/autonomous.py` | 四层防御方法 + 执行流程整合 |
| `src/agent_loop.py` | 新增 `inject_system_message()` 方法 |
| `src/session_event_stream.py` | 新增 `SYSTEM_MESSAGE` 事件类型 |
| `tests/test_autonomous.py` | 四层防御单元测试覆盖 |

---

## 问题分析

### 当前状态

| 组件 | 当前限制 | 确切位置 |
|------|---------|---------|
| **AutonomousExplorer** | 100 轮/任务 | `src/autonomous.py` 第 428 行: `self.agent.max_iterations = 100` |
| **AgentLoop** | 100 轮（默认）| `src/agent_loop.py` 第 138 行: `max_iterations: int = 100` |
| **Harness** | 100 轮（默认）| `src/harness.py` 第 80 行: `MAX_ITERATIONS = 100` |
| **RalphLoop 安全上限** | 1000 轮 + 8 小时 | `src/ralph_loop.py` 第 84-85 行 |

### 问题现象

用户反馈自主探索时经常被 100 轮循环上限卡住，导致：

1. **探索深度不足**: 复杂代码分析任务无法完成
2. **任务中断**: 长周期任务被迫终止，需手动重启
3. **效率损失**: 已积累的上下文因限制被丢弃

### 根因分析

| 问题根因 | 影响范围 |
|---------|---------|
| **硬编码限制**: 100 轮上限硬编码在 autonomous.py | 无法按需调整 |
| **单一终止条件**: 仅迭代计数，无智能判断 | 无法识别"有进展但需更多轮次"的场景 |
| **无预算警告**: Agent 无感知剩余预算 | 无法提前规划收尾 |
| **无进度检测**: 不区分"有效探索"与"空转循环" | 无法及时终止无意义循环 |

### 与行业最佳实践对比

| 行业标准 | seed-agent 当前状态 | 差距 |
|---------|---------------------|------|
| **多层防御** (4层: 迭代/Token/进度/时间) | 单层迭代限制 | 缺少智能终止 |
| **渐进式预算警告** (70% 提示) | 无警告机制 | Agent 无法主动收尾 |
| **任务类型分层** (简单/复杂/研究) | 固定 100 轮 | 无法适配任务复杂度 |
| **递减重试预算** (15→10→5) | 无重试机制 | 重试时无法收紧预算 |

---

## 方案设计

### 方案概述: A+C 组合

| 方案 | 核心机制 | 改动范围 |
|------|---------|---------|
| **方案 A: 配置化上限** | 将硬编码改为可配置参数 | `shared_config.py`, `autonomous.py` |
| **方案 C: 渐进式预算** | 多层防御 + 预算警告 + 进度检测 | `autonomous.py`, `harness.py` |

### 设计架构

```
┌─────────────────────────────────────────────────────────────┐
│                    配置层 (方案 A)                            │
│  AutonomousConfig.max_iterations_per_task                   │
│  AutonomousConfig.progress_detection_window                 │
│  AutonomousConfig.budget_warning_threshold                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    执行层 (方案 C)                            │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ 预算警告注入    │  │ 进度检测窗口    │                  │
│  │ (70%/90%)      │  │ (no_progress)   │                  │
│  └─────────────────┘  └─────────────────┘                  │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ 时间断路器      │  │ 递减重试预算    │                  │
│  │ (per_task)     │  │ (retry decay)   │                  │
│  └─────────────────┘  └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    安全层 (继承现有)                          │
│  RALPH_MAX_ITERATIONS = 1000                                │
│  RALPH_MAX_DURATION = 8 hours                               │
│  check_safety_limits()                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 方案 A: 配置化上限

### 新增配置字段

**位置**: `src/shared_config.py` - `AutonomousConfig` 类

```python
@dataclass
class AutonomousConfig:
    # 现有字段...
    idle_timeout_hours: int = 2
    llm_call_timeout_seconds: int = 300
    iteration_timeout_seconds: int = 600
    
    # 新增字段 (方案 A)
    max_iterations_per_task: int = 100       # 单任务迭代上限（可配置）
    max_iterations_high: int = 300           # 高复杂度任务上限
    max_iterations_research: int = 500       # 研究型任务上限
    max_duration_per_task: int = 1800        # 单任务时间上限（秒，30分钟）
```

### 配置文件示例

```json
{
  "autonomous": {
    "idle_timeout_hours": 2,
    "max_iterations_per_task": 200,
    "max_iterations_high": 400,
    "max_iterations_research": 600,
    "max_duration_per_task": 3600
  }
}
```

### 代码改动点

| 文件 | 改动 | 原代码 | 新代码 |
|------|------|--------|--------|
| `src/autonomous.py` 第 428 行 | 使用配置值 | `self.agent.max_iterations = 100` | `self.agent.max_iterations = autonomous_config.max_iterations_per_task` |
| `src/autonomous.py` 第 77-78 行 | 引用配置 | `RALPH_MAX_ITERATIONS = 1000` | 使用 `AutonomousConfig` 字段作为上限 |

---

## 方案 C: 渐进式预算机制

### Layer 1: 预算警告注入

**机制**: 在剩余预算达到阈值时，注入警告消息到 Agent 对话历史。

**设计**:

```python
# src/autonomous.py - 新增方法
async def _inject_budget_warning(self, current: int, max: int) -> None:
    """注入预算警告消息"""
    remaining = max - current
    percentage = current / max * 100
    
    if percentage >= self.config.budget_warning_threshold:  # 70%
        warning_msg = (
            f"[BUDGET WARNING] 已使用 {current}/{max} 轮迭代 ({percentage:.0f}%)。"
            f"剩余 {remaining} 轮。建议开始总结和收尾工作。"
        )
        await self.agent.inject_system_message(warning_msg)
    
    if percentage >= 90:  # 90% 紧急警告
        urgent_msg = (
            f"[BUDGET URGENT] 已使用 {current}/{max} 轮 ({percentage:.0f}%)。"
            f"仅剩 {remaining} 轮。请立即执行最终操作。"
        )
        await self.agent.inject_system_message(urgent_msg)
```

**配置字段**:

```python
@dataclass
class AutonomousConfig:
    budget_warning_threshold: float = 0.70   # 70% 时注入警告
    budget_urgent_threshold: float = 0.90    # 90% 时注入紧急警告
```

### Layer 2: 进度检测窗口

**机制**: 检测连续 N 轮无有效工具调用，判定为"空转循环"，提前终止。

**设计**:

```python
# src/autonomous.py - 新增方法
def _check_progress_window(self) -> bool:
    """检查进度窗口，判断是否有有效进展
    
    Returns:
        True: 有进展，继续执行
        False: 无进展，建议终止
    """
    window_size = self.config.progress_detection_window  # 默认 5 轮
    
    # 获取最近 N 轮的工具调用记录
    recent_actions = self._action_history[-window_size:]
    
    # 检查是否有实质性工具调用（排除 ask_user, search_history 等）
    meaningful_actions = [
        a for a in recent_actions
        if a.tool in self.config.meaningful_tools  # file_read, file_write, code_as_policy 等
    ]
    
    if len(meaningful_actions) == 0:
        self.logger.warning(
            f"连续 {window_size} 轮无有效工具调用，判定为空转循环"
        )
        return False
    
    return True
```

**配置字段**:

```python
@dataclass
class AutonomousConfig:
    progress_detection_window: int = 5       # 进度检测窗口大小
    meaningful_tools: list[str] = field(     # 有意义的工具列表
        default_factory=lambda: [
            "file_read", "file_write", "file_edit",
            "code_as_policy", "search_grep", "search_glob"
        ]
    )
```

### Layer 3: 时间断路器

**机制**: 单任务时间上限，防止长时间无产出运行。

**设计**:

```python
# src/autonomous.py - 新增方法
def _check_time_circuit_breaker(self) -> bool:
    """检查时间断路器
    
    Returns:
        True: 未超时，继续执行
        False: 超时，强制终止
    """
    elapsed = time.time() - self._task_start_time
    max_duration = self.config.max_duration_per_task  # 默认 30 分钟
    
    if elapsed >= max_duration:
        self.logger.warning(
            f"任务执行时间 {elapsed:.0f}s 超过上限 {max_duration}s，触发断路器"
        )
        return False
    
    # 在 80% 时间时注入时间警告
    if elapsed >= max_duration * 0.80:
        remaining = max_duration - elapsed
        await self.agent.inject_system_message(
            f"[TIME WARNING] 已运行 {elapsed:.0f}s，剩余 {remaining:.0f}s。"
            f"请尽快完成当前操作。"
        )
    
    return True
```

### Layer 4: 递减重试预算

**机制**: 任务失败重试时，递减迭代预算，避免无限重试。

**设计**:

```python
# src/autonomous.py - 新增属性和方法
class AutonomousExplorer:
    def __init__(self):
        self._retry_count: int = 0
        self._retry_decay_factors: list[float] = [1.0, 0.5, 0.25]  # 首次100%, 二次50%, 三次25%
    
    def _get_retry_budget(self) -> int:
        """获取当前重试的迭代预算"""
        base_budget = self.config.max_iterations_per_task
        
        if self._retry_count >= len(self._retry_decay_factors):
            return 0  # 超过重试上限，不再执行
        
        decay_factor = self._retry_decay_factors[self._retry_count]
        return int(base_budget * decay_factor)
```

---

## 整合设计: 四层防御体系

### 执行流程

```python
# src/autonomous.py - _execute_autonomous_task 改造
async def _execute_autonomous_task(self) -> None:
    """执行自主探索任务（带多层防御）"""
    self._task_start_time = time.time()
    self._iteration_count = 0
    self._action_history = []
    
    # 获取预算（考虑重试递减）
    max_iterations = self._get_retry_budget()
    
    # 设置 AgentLoop 参数
    self.agent.max_iterations = max_iterations
    
    # Ralph Loop 执行
    while True:
        # === 多层防御检查 ===
        
        # Layer 1: 预算警告注入
        await self._inject_budget_warning(
            current=self._iteration_count,
            max=max_iterations
        )
        
        # Layer 2: 进度检测窗口
        if not self._check_progress_window():
            self.logger.info("进度检测判定空转，提前终止")
            break
        
        # Layer 3: 时间断路器
        if not self._check_time_circuit_breaker():
            self.logger.info("时间断路器触发，强制终止")
            break
        
        # Layer 4: 安全上限检查（继承现有）
        if self._check_safety_limits():
            self.logger.info("安全上限触发，终止任务")
            break
        
        # === 执行一轮迭代 ===
        result = await self._run_single_iteration()
        self._iteration_count += 1
        self._action_history.extend(result.tool_calls)
        
        # === 检查完成条件 ===
        if self._check_completion_criteria(result):
            self.logger.info("任务完成条件满足，结束探索")
            break
```

### 终止条件优先级

| 优先级 | 条件 | 触发时机 | 行为 |
|--------|------|---------|------|
| **最高** | 安全上限 | iteration >= 1000 或 duration >= 8h | 强制终止（继承现有） |
| **高** | 时间断路器 | elapsed >= max_duration_per_task | 强制终止 |
| **中** | 进度检测空转 | 连续 N 轮无有效工具调用 | 建议终止 |
| **低** | 预算警告 | iteration >= 70%/90% threshold | 注入警告，继续 |
| **最低** | 完成条件 | SOP 完成/外部验证通过 | 正常结束 |

---

## 完整配置字段定义

```python
# src/shared_config.py
@dataclass
class AutonomousConfig:
    """自主探索配置（方案 A+C 整合）"""
    
    # === 现有字段 ===
    idle_timeout_hours: int = 2
    llm_call_timeout_seconds: int = 300
    iteration_timeout_seconds: int = 600
    consecutive_failure_threshold: int = 3
    
    # === 方案 A: 配置化上限 ===
    max_iterations_per_task: int = 100       # 单任务迭代上限
    max_iterations_high: int = 300           # 高复杂度任务上限
    max_iterations_research: int = 500       # 研究型任务上限
    max_duration_per_task: int = 1800        # 单任务时间上限（秒）
    max_retry_count: int = 3                 # 最大重试次数
    
    # === 方案 C: 渐进式预算 ===
    budget_warning_threshold: float = 0.70   # 预算警告阈值
    budget_urgent_threshold: float = 0.90    # 紧急警告阈值
    progress_detection_window: int = 5       # 进度检测窗口
    time_warning_threshold: float = 0.80     # 时间警告阈值
    retry_decay_factors: list[float] = field(
        default_factory=lambda: [1.0, 0.5, 0.25]
    )
    meaningful_tools: list[str] = field(
        default_factory=lambda: [
            "file_read", "file_write", "file_edit",
            "code_as_policy", "search_grep", "search_glob"
        ]
    )
```

---

## 实施步骤

### Phase 1: 配置化上限（方案 A）

| 步骤 | 任务 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 1.1 | 新增配置字段 | `src/shared_config.py` | 0.5 天 |
| 1.2 | 改用配置值 | `src/autonomous.py` 第 428 行 | 0.5 天 |
| 1.3 | 更新文档 | `docs/AGENTS.md` | 0.5 天 |
| 1.4 | 单元测试 | `tests/test_autonomous.py` | 0.5 天 |

**Phase 1 总工作量**: 2 天

### Phase 2: 预算警告注入（方案 C Layer 1）

| 步骤 | 任务 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 2.1 | 实现 `_inject_budget_warning()` | `src/autonomous.py` | 0.5 天 |
| 2.2 | 实现 `inject_system_message()` | `src/agent_loop.py` | 0.5 天 |
| 2.3 | 配置字段 | `src/shared_config.py` | 0.25 天 |
| 2.4 | 单元测试 | `tests/test_autonomous.py` | 0.5 天 |

**Phase 2 总工作量**: 1.75 天

### Phase 3: 进度检测窗口（方案 C Layer 2）

| 步骤 | 任务 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 3.1 | 实现 `_check_progress_window()` | `src/autonomous.py` | 1 天 |
| 3.2 | 工具调用记录收集 | `src/autonomous.py` | 0.5 天 |
| 3.3 | 配置字段 | `src/shared_config.py` | 0.25 天 |
| 3.4 | 单元测试 | `tests/test_autonomous.py` | 0.5 天 |

**Phase 3 总工作量**: 2.25 天

### Phase 4: 时间断路器（方案 C Layer 3）

| 步骤 | 任务 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 4.1 | 实现 `_check_time_circuit_breaker()` | `src/autonomous.py` | 0.5 天 |
| 4.2 | 配置字段 | `src/shared_config.py` | 0.25 天 |
| 4.3 | 单元测试 | `tests/test_autonomous.py` | 0.5 天 |

**Phase 4 总工作量**: 1.25 天

### Phase 5: 递减重试预算（方案 C Layer 4）

| 步骤 | 任务 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 5.1 | 实现 `_get_retry_budget()` | `src/autonomous.py` | 0.5 天 |
| 5.2 | 重试计数逻辑 | `src/autonomous.py` | 0.5 天 |
| 5.3 | 配置字段 | `src/shared_config.py` | 0.25 天 |
| 5.4 | 单元测试 | `tests/test_autonomous.py` | 0.5 天 |

**Phase 5 总工作量**: 1.75 天

### Phase 6: 整合与集成测试

| 步骤 | 任务 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 6.1 | 整合四层防御到执行流程 | `src/autonomous.py` | 1 天 |
| 6.2 | 集成测试 | `tests/test_autonomous_integration.py` | 1 天 |
| 6.3 | 文档更新 | `docs/`, `AGENTS.md` | 0.5 天 |

**Phase 6 总工作量**: 2.5 天

---

## 总工作量汇总

| Phase | 工作量 | 累计 |
|-------|--------|------|
| Phase 1 (配置化) | 2 天 | 2 天 |
| Phase 2 (预算警告) | 1.75 天 | 3.75 天 |
| Phase 3 (进度检测) | 2.25 天 | 6 天 |
| Phase 4 (时间断路器) | 1.25 天 | 7.25 天 |
| Phase 5 (递减重试) | 1.75 天 | 9 天 |
| Phase 6 (整合测试) | 2.5 天 | 11.5 天 |

**预计总工作量**: 11.5 天（约 2 周）

---

## 预期收益

### 功能收益

| 收益 | 描述 |
|------|------|
| **可配置上限** | 用户可按任务复杂度调整迭代限制 |
| **智能终止** | 进度检测避免空转循环浪费资源 |
| **预算感知** | Agent 可提前规划收尾，减少强制中断 |
| **重试收紧** | 递减预算避免无限重试浪费 |
| **时间保护** | 单任务时间上限防止长时间无产出 |

### 性能收益

| 场景 | 当前状态 | 改进后 |
|------|---------|--------|
| 复杂代码分析 | 100 轮强制中断 | 可配置至 300-500 轮 |
| 空转循环 | 无感知，持续到 100 轮 | 5 轮检测后提前终止 |
| 任务超时 | 无单任务时间限制 | 30 分钟断路器 |
| 重试浪费 | 每次重试 100 轮 | 递减: 100→50→25 |

### 安全收益

| 收益 | 描述 |
|------|------|
| **多层防御** | 4 层独立检查，降低失控风险 |
| **渐进警告** | 70%/90% 提醒，Agent 主动收尾 |
| **继承安全上限** | 1000 轮 + 8 小时作为最终兜底 |

---

## 风险评估

### 风险清单

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| **配置过高导致失控** | 中 | 保留安全上限（1000 轮 + 8 小时）作为兜底 |
| **进度检测误判** | 中 | 配置 `meaningful_tools` 精细化，避免误判 |
| **预算警告被忽略** | 低 | 多次警告 + 紧急警告 + 最终强制终止 |
| **时间断路器打断有效任务** | 低 | 配置 `max_duration_per_task` 按任务类型调整 |
| **重试预算不足** | 低 | 可配置 `retry_decay_factors`，放宽递减比例 |

### 回滚策略

| 组件 | 回滚方式 |
|------|---------|
| 配置字段 | 移除新增字段，恢复硬编码 |
| 四层防御 | 移除检查逻辑，保留原始迭代上限检查 |
| 单元测试 | 删除新增测试文件 |

---

## 测试计划

### 单元测试

| 测试 | 测试目标 | 预期结果 |
|------|---------|---------|
| `test_config_fields` | 配置字段加载 | 新增字段正确解析 |
| `test_budget_warning_70` | 70% 预算警告注入 | 消息正确注入对话历史 |
| `test_budget_warning_90` | 90% 紧急警告注入 | 紧急消息注入 |
| `test_progress_window_detection` | 进度检测空转识别 | 连续 5 轮无有效工具判定为空转 |
| `test_progress_window_valid` | 进度检测有效识别 | 有有效工具调用判定为有进展 |
| `test_time_circuit_breaker` | 时间断路器触发 | 超时后强制终止 |
| `test_time_warning` | 时间警告注入 | 80% 时间注入警告 |
| `test_retry_budget_decay` | 递减预算计算 | 重试预算正确递减 |
| `test_integration_all_layers` | 四层防御整合 | 各层按优先级正确触发 |

### 集成测试

| 测试 | 场景 | 预期行为 |
|------|------|---------|
| `test_complex_analysis_task` | 复杂代码分析（300 轮配置）| 完整执行，预算警告在 70% 出现 |
| `test_empty_loop_task` | 空转循环场景 | 5 轮后进度检测终止 |
| `test_timeout_task` | 长时间任务 | 30 分钟断路器终止 |
| `test_retry_scenario` | 任务失败重试 | 重试预算递减: 100→50→25 |
| `test_safety_limit` | 超过配置上限 | 安全上限（1000 轮）兜底 |

---

## 相关文档

| 文档 | 关系 |
|------|------|
| [long_cycle_loop_enhancement_design.md](long_cycle_loop_enhancement_design.md) | RalphLoop 安全上限继承 |
| [ralph_loop.md](ralph_loop.md) | Ralph Loop 概念理解 |
| [src/AGENTS.md](../src/AGENTS.md) | AutonomousExplorer 实现文档 |
| [docs/AGENTS.md](AGENTS.md) | 设计文档索引 |

---

## 讨论记录

### 用户需求

> "ulw seed agent 在自主探索时，经常被 100 轮循环上限卡住，你评估一下是否需要放宽循环上限？和我讨论方案，在我认可后生成方案文档"

### 方案讨论

用户选择 **方案 A（配置化上限）+ 方案 C（渐进式预算）** 组合设计。

### 关键决策

| 决策点 | 用户确认 |
|--------|---------|
| 配置化上限 | ✅ 同意将硬编码改为可配置 |
| 渐进式预算警告 | ✅ 同意 70%/90% 阈值设计 |
| 进度检测窗口 | ✅ 同意 5 轮空转检测 |
| 时间断路器 | ✅ 同意单任务时间上限 |
| 递减重试预算 | ✅ 同意 100→50→25 递减比例 |
| 安全上限继承 | ✅ 同意保留 1000 轮 + 8 小时兜底 |

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-05-04 | 初始版本，方案讨论完成 |
| v2.0 | 2026-05-04 | 方案 A+C 组合实施完成，四层防御体系落地 |