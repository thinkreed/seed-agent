# 长周期自主任务增强设计文档

> **决策摘要**：在现有 AgentLoop 基础上引入 Ralph Loop 理念，形成三层循环架构，增强长周期自主任务的确定性完成能力。

---

## 一、背景与动机

### 1.1 现有问题

当前 seed-agent 的循环架构存在以下瓶颈：

| 问题 | 表现 | 影响 |
|------|------|------|
| **上下文漂移** | 长对话通过 `_maybe_summarize()` 压缩历史，摘要丢失细节 | 任务偏离原始目标 |
| **主观完成判断** | 模型决定"完成" = 返回文本无 `tool_calls` | 可能过早退出或陷入无效循环 |
| **迭代上限限制** | `max_iterations=30-100` 硬上限 | 长周期任务无法完成 |
| **状态不持久** | `history` 在进程终止时丢失（事后保存） | 无法恢复中断任务 |

### 1.2 Ralph Loop 理念

Ralph Loop（源自 Geoffrey Huntley，2025）的核心机制：

```
外部循环控制 + 状态持久化 + 完成验证
```

- **外部循环**：拦截 AI"退出"信号，强制重新注入任务
- **状态持久化**：进度保存于文件系统/Git/测试结果
- **完成验证**：由外部客观标准（测试通过/DONE标志）决定，而非模型自判

### 1.3 目标

在不破坏交互式场景的前提下，为**长周期自主任务**引入确定性完成机制：

- 支持理论无限迭代（外部验证驱动）
- 消除上下文漂移风险
- 客观完成标准
- 任务可恢复（进程崩溃后继续）

---

## 二、现状架构分析

### 2.1 当前循环体系

```
main.py
   │
   ├── AgentLoop (src/agent_loop.py)
   │     │
   │     ├── 触发: 每条用户消息
   │     ├── max_iterations: 30
   │     ├── summary_interval: 10轮 / 75%上下文
   │     ├── 退出: 无tool_calls → 返回文本
   │     └── 支持: interrupt(user_input)
   │
   ├── AutonomousExplorer (src/autonomous.py)
   │     │
   │     ├── 触发: 30分钟空闲
   │     ├── 检查周期: 30秒
   │     ├── max_iterations: 100 (临时提升)
   │     ├── 退出: TODO完成或空响应
   │     └── SOP: auto/自主探索 SOP.md
   │
   └── TaskScheduler (src/scheduler.py)
         │
         ├── autodream: 每12小时
         ├── autonomous_explore: 每15分钟
         └── health_check: 每1小时
```

### 2.2 关键代码位置

| 文件 | 关键方法 | 功能 |
|------|----------|------|
| `src/agent_loop.py` | `run()`, `stream_run()` | 核心迭代循环 |
| `src/agent_loop.py` | `_maybe_summarize()` | 上下文压缩 |
| `src/agent_loop.py` | `_build_messages()` | 消息构建 |
| `src/autonomous.py` | `_idle_monitor_loop()` | 空闲监控循环 |
| `src/autonomous.py` | `_execute_autonomous_task()` | 自主任务执行 |
| `src/autonomous.py` | `_build_autonomous_prompt()` | Prompt 构建 |

### 2.3 已有的 Ralph Loop 特征

| 特征 | 现有实现 | 缺失 |
|------|----------|------|
| 外部循环控制 | `_idle_monitor_loop()` | ✓ 有 |
| 状态持久化 | TODO.md + L4 session | ✓ 有 |
| SOP 驱动 | `auto/自主探索 SOP.md` | ✓ 有 |
| **外部完成验证** | ❌ 无 | 需新增 |
| **上下文重置** | ❌ 无 | 需新增 |
| **退出拦截** | ❌ 无 | 需新增 |

---

## 三、目标架构设计

### 3.1 三层循环架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      三层循环架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Layer 1: AgentLoop (不变)                                    ││
│  │ ───────────────────────                                      ││
│  │                                                              ││
│  │ 角色: 单次对话执行引擎                                        ││
│  │ 触发: 每条用户消息                                            ││
│  │ 限制: max_iterations=30, summary_interval=10                 ││
│  │ 特性: 支持 interrupt(user_input)                             ││
│  │ 适用: 交互式问答、单步任务                                    ││
│  │                                                              ││
│  │ 代码位置: src/agent_loop.py (不改动)                         ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Layer 2: AutonomousExplorer (增强)                           ││
│  │ ───────────────────────────────────                          ││
│  │                                                              ││
│  │ 角色: 中周期自主任务执行器                                    ││
│  │ 触发: 30分钟空闲                                              ││
│  │                                                              ││
│  │ 新增特性:                                                    ││
│  │   ✓ completion_promise 检测                                  ││
│  │   ✓ 可选上下文重置                                           ││
│  │   ✓ 防无限循环上限                                           ││
│  │                                                              ││
│  │ 适用: TODO执行、探索性任务                                    ││
│  │                                                              ││
│  │ 代码位置: src/autonomous.py (改动)                           ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Layer 3: RalphLoop (新增)                                    ││
│  │ ───────────────────                                          ││
│  │                                                              ││
│  │ 角色: 长周期确定性任务执行器                                  ││
│  │ 触发: 显式调用 / 任务文件触发                                 ││
│  │                                                              ││
│  │ 核心特性:                                                    ││
│  │   ✓ 外部验证驱动完成                                         ││
│  │   ✓ 每次迭代新鲜上下文                                       ││
│  │   ✓ 状态持久于文件系统                                       ││
│  │   ✓ 防无限循环上限                                           ││
│  │                                                              ││
│  │ 适用: 系统重构、测试驱动开发、多模块批量任务                  ││
│  │                                                              ││
│  │ 代码位置: src/ralph_loop.py (新增)                           ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 层级职责边界

| 层级 | 迭代上限 | 上下文策略 | 完成判断 | 用户介入 |
|------|----------|------------|----------|----------|
| Layer 1 | 30 | 累积+压缩 | 模型自判 | ✓ 支持 |
| Layer 2 | 100-200 | 可选重置 | 模型+验证 | 非实时 |
| Layer 3 | 外部驱动 | 强制重置 | 外部验证 | 事后检查 |

---

## 四、组件设计详解

### 4.1 Layer 1: AgentLoop (不变)

**设计决策**：保持现状，作为所有循环的底层执行引擎。

理由：
- 交互式场景需要 `interrupt` 支持
- 单次对话迭代上限足够
- 压缩机制对短对话有效

**不变部分**：
- `src/agent_loop.py` 全部代码
- `max_iterations=30`
- `summary_interval=10`
- `_maybe_summarize()` 机制

### 4.2 Layer 2: AutonomousExplorer (增强)

**新增特性**：

#### A. completion_promise 检测

```python
# 新增配置
COMPLETION_PROMISE_FILE = ".seed/completion_promise"
COMPLETION_PROMISE_TOKENS = ["DONE", "COMPLETE", "TASK_FINISHED"]

# 新增方法
def _check_completion_promise(self) -> bool:
    """检查外部完成标志"""
    if Path(COMPLETION_PROMISE_FILE).exists():
        content = Path(COMPLETION_PROMISE_FILE).read_text().strip()
        return content in COMPLETION_PROMISE_TOKENS
    return False

# 改动退出逻辑
async def _execute_autonomous_task(self):
    # ... 原有逻辑
    
    # 新增: 检查 completion_promise
    if self._check_completion_promise():
        logger.info("Completion promise detected, exiting Ralph loop")
        Path(COMPLETION_PROMISE_FILE).unlink()  # 清除标志
        return "DONE"
```

#### B. 可选上下文重置

```python
# 新增配置
CONTEXT_RESET_ENABLED = True  # 默认开启
CONTEXT_RESET_INTERVAL = 5    # 每5轮迭代重置

# 新增方法
async def _reset_context_if_needed(self, iteration: int):
    """条件性重置上下文"""
    if CONTEXT_RESET_ENABLED and iteration % CONTEXT_RESET_INTERVAL == 0:
        # 保存关键状态
        self._persist_critical_state()
        
        # 重置 history
        self.agent.history.clear()
        
        # 重新注入任务 prompt
        prompt = self._load_fresh_task_prompt()
        self.agent.history.append({"role": "user", "content": prompt})
        
        logger.info(f"Context reset at iteration {iteration}")
```

#### C. 防无限循环上限

```python
# 新增配置
RALPH_MAX_ITERATIONS = 1000  # 理论上限
RALPH_MAX_DURATION = 8 * 60 * 60  # 8小时最大执行时间

# 新增检查
async def _execute_autonomous_task(self):
    start_time = time.time()
    
    for iteration in range(RALPH_MAX_ITERATIONS):
        # 时间上限检查
        if time.time() - start_time > RALPH_MAX_DURATION:
            logger.warning("Ralph loop exceeded max duration, forcing exit")
            break
        
        # ... 原有迭代逻辑
```

### 4.3 Layer 3: RalphLoop (新增)

**新建文件**：`src/ralph_loop.py`

#### 核心类设计

```python
"""Ralph Loop: 长周期确定性任务执行器"""

import time
import asyncio
from pathlib import Path
from typing import Optional, Callable, List
from enum import Enum
import logging

logger = logging.getLogger("seed_agent.ralph")

SEED_DIR = Path.home() / ".seed"


class CompletionType(Enum):
    """完成验证类型"""
    TEST_PASS = "test_pass"         # 测试通过
    FILE_EXISTS = "file_exists"     # 目标文件存在
    MARKER_FILE = "marker_file"     # 完成标志文件
    GIT_CLEAN = "git_clean"         # Git 工作区干净
    CUSTOM_CHECK = "custom_check"   # 自定义验证函数


class RalphLoop:
    """Ralph Loop 执行器
    
    核心机制:
    1. 外部验证驱动完成
    2. 每次迭代新鲜上下文
    3. 状态持久于文件系统
    4. 防无限循环保护
    """
    
    # 默认配置
    MAX_ITERATIONS = 1000
    MAX_DURATION = 8 * 60 * 60  # 8小时
    ITERATION_INTERVAL = 5      # 上下文重置间隔
    
    def __init__(
        self,
        agent_loop,
        completion_type: CompletionType,
        completion_criteria: dict,
        task_prompt_path: Path,
        on_iteration_complete: Callable = None
    ):
        self.agent = agent_loop
        self.completion_type = completion_type
        self.completion_criteria = completion_criteria
        self.task_prompt_path = task_prompt_path
        self.on_iteration_complete = on_iteration_complete
        
        self._iteration_count: int = 0
        self._start_time: float = 0
        self._state_file: Path = SEED_DIR / "ralph_state.json"
    
    # === 核心方法 ===
    
    async def run(self) -> str:
        """执行 Ralph Loop"""
        self._start_time = time.time()
        self._iteration_count = 0
        
        # 加载或初始化状态
        self._load_or_init_state()
        
        while True:
            self._iteration_count += 1
            
            # 1. 安全检查
            if self._check_safety_limits():
                break
            
            # 2. 上下文重置（新鲜上下文）
            self._reset_context()
            
            # 3. 加载任务 prompt
            prompt = self._load_task_prompt()
            
            # 4. 执行一轮 Agent Loop
            response = await self.agent.run(prompt)
            
            # 5. 持久化状态
            self._persist_state(response)
            
            # 6. 外部完成验证
            if self._check_completion():
                logger.info(f"Ralph Loop completed at iteration {self._iteration_count}")
                self._cleanup()
                return "DONE"
            
            # 7. 回调通知
            if self.on_iteration_complete:
                await self._invoke_callback()
            
            # 8. 等待下一轮
            await asyncio.sleep(1)
        
        return self._generate_status_report()
    
    # === 完成验证 ===
    
    def _check_completion(self) -> bool:
        """外部完成验证"""
        validators = {
            CompletionType.TEST_PASS: self._check_test_pass,
            CompletionType.FILE_EXISTS: self._check_file_exists,
            CompletionType.MARKER_FILE: self._check_marker_file,
            CompletionType.GIT_CLEAN: self._check_git_clean,
            CompletionType.CUSTOM_CHECK: self._check_custom,
        }
        
        validator = validators.get(self.completion_type)
        if validator:
            return validator()
        return False
    
    def _check_test_pass(self) -> bool:
        """检查测试通过率"""
        required_rate = self.completion_criteria.get("pass_rate", 100)
        test_command = self.completion_criteria.get("test_command", "pytest tests/ -v")
        
        # 执行测试命令
        import subprocess
        result = subprocess.run(test_command, shell=True, capture_output=True)
        
        # 解析测试结果
        # ... (根据测试框架解析)
        pass_rate = self._parse_test_pass_rate(result.stdout)
        
        return pass_rate >= required_rate
    
    def _check_file_exists(self) -> bool:
        """检查目标文件存在"""
        files = self.completion_criteria.get("files", [])
        return all(Path(f).exists() for f in files)
    
    def _check_marker_file(self) -> bool:
        """检查完成标志文件"""
        marker_path = self.completion_criteria.get("marker_path", SEED_DIR / "completion_marker")
        marker_content = self.completion_criteria.get("marker_content", "DONE")
        
        if marker_path.exists():
            return marker_path.read_text().strip() == marker_content
        return False
    
    def _check_git_clean(self) -> bool:
        """检查 Git 工作区状态"""
        import subprocess
        result = subprocess.run(
            "git status --porcelain",
            shell=True,
            capture_output=True,
            cwd=self.completion_criteria.get("repo_path", ".")
        )
        return result.stdout.strip() == ""
    
    def _check_custom(self) -> bool:
        """自定义验证函数"""
        checker = self.completion_criteria.get("checker")
        if checker and callable(checker):
            return checker()
        return False
    
    # === 上下文管理 ===
    
    def _reset_context(self):
        """重置上下文（新鲜上下文）"""
        # 可选: 保留部分关键信息
        preserved = self._extract_critical_context()
        
        # 清空 history
        self.agent.history.clear()
        
        # 重新注入保留信息（如有）
        if preserved:
            self.agent.history.append({
                "role": "system",
                "content": f"[迭代 {self._iteration_count} 状态摘要]\n{preserved}"
            })
        
        logger.info(f"Context reset at iteration {self._iteration_count}")
    
    def _load_task_prompt(self) -> str:
        """加载任务 prompt（从文件）"""
        if self.task_prompt_path.exists():
            return self.task_prompt_path.read_text()
        
        # 默认 prompt
        return f"继续执行任务。当前迭代: {self._iteration_count}"
    
    # === 状态持久化 ===
    
    def _load_or_init_state(self):
        """加载或初始化状态"""
        if self._state_file.exists():
            import json
            state = json.loads(self._state_file.read_text())
            self._iteration_count = state.get("iteration", 0)
            logger.info(f"Resumed Ralph Loop from iteration {self._iteration_count}")
    
    def _persist_state(self, response: str):
        """持久化当前状态"""
        import json
        state = {
            "iteration": self._iteration_count,
            "start_time": self._start_time,
            "last_response": response[:500],  # 截断
            "timestamp": time.time()
        }
        self._state_file.write_text(json.dumps(state, indent=2))
    
    # === 安全机制 ===
    
    def _check_safety_limits(self) -> bool:
        """检查安全上限"""
        # 迭代上限
        if self._iteration_count >= self.MAX_ITERATIONS:
            logger.warning(f"Ralph Loop exceeded max iterations ({self.MAX_ITERATIONS})")
            return True
        
        # 时间上限
        elapsed = time.time() - self._start_time
        if elapsed >= self.MAX_DURATION:
            logger.warning(f"Ralph Loop exceeded max duration ({self.MAX_DURATION}s)")
            return True
        
        return False
    
    # === 辅助方法 ===
    
    def _extract_critical_context(self) -> Optional[str]:
        """提取关键上下文（可选）"""
        # 从 agent.history 提取关键决策/发现
        # 简化实现: 提取最后一条 assistant 消息的摘要
        if self.agent.history:
            last_assistant = None
            for msg in reversed(self.agent.history):
                if msg.get("role") == "assistant" and msg.get("content"):
                    last_assistant = msg["content"]
                    break
            if last_assistant:
                return f"上次执行摘要: {last_assistant[:300]}"
        return None
    
    def _cleanup(self):
        """清理状态文件"""
        if self._state_file.exists():
            self._state_file.unlink()
    
    def _generate_status_report(self) -> str:
        """生成状态报告"""
        elapsed = time.time() - self._start_time
        return f"""
Ralph Loop Status Report:
- Iterations: {self._iteration_count}
- Duration: {elapsed/60:.1f} minutes
- Exit Reason: Safety limit reached
- State File: {self._state_file}
"""
```

#### 工具注册

```python
# src/tools/ralph_tools.py

def start_ralph_loop(
    task_prompt_file: str,
    completion_type: str = "marker_file",
    max_iterations: int = 1000
) -> str:
    """启动 Ralph Loop
    
    Args:
        task_prompt_file: 任务描述文件路径
        completion_type: 完成验证类型 (test_pass/file_exists/marker_file/git_clean)
        max_iterations: 最大迭代次数
    
    Returns:
        Ralph Loop ID 和状态
    """

def write_completion_marker(content: str = "DONE") -> str:
    """写入完成标志
    
    用于 Ralph Loop 的 marker_file 完成验证
    """

def check_ralph_status() -> str:
    """检查 Ralph Loop 状态"""
```

---

## 五、配置参数设计

### 5.1 新增配置项

在 `config/config.json` 或独立的 `ralph_config.json` 中：

```json
{
  "ralph_loop": {
    "max_iterations": 1000,
    "max_duration_hours": 8,
    "context_reset_enabled": true,
    "context_reset_interval": 5,
    "completion_types": ["marker_file", "test_pass"],
    "state_dir": "~/.seed/ralph",
    
    "autonomous_enhancement": {
      "completion_promise_enabled": true,
      "completion_promise_file": "~/.seed/completion_promise",
      "completion_tokens": ["DONE", "COMPLETE", "TASK_FINISHED"],
      "context_reset_on_long_task": true
    }
  }
}
```

### 5.2 环境变量支持

```bash
RALPH_MAX_ITERATIONS=1000
RALPH_MAX_DURATION=8h
RALPH_CONTEXT_RESET=true
RALPH_STATE_DIR=~/.seed/ralph
```

---

## 六、改动范围与优先级

### 6.1 改动清单

| 优先级 | 文件 | 改动内容 | 复杂度 |
|--------|------|----------|--------|
| P0 | `src/autonomous.py` | completion_promise 检测 | 低 |
| P1 | `src/autonomous.py` | 可选上下文重置 | 中 |
| P1 | `src/ralph_loop.py` | 新建 RalphLoop 类 | 高 |
| P2 | `src/tools/ralph_tools.py` | 新建工具注册 | 低 |
| P2 | `config/config.json` | 新增 ralph 配置 | 低 |
| P3 | `src/scheduler.py` | 集成 RalphLoop 任务 | 中 |
| P3 | `tests/test_ralph.py` | 单元测试 | 中 |

### 6.2 不改动部分

| 文件 | 理由 |
|------|------|
| `src/agent_loop.py` | 作为底层引擎保持不变 |
| `src/client.py` | LLM 调用层无需改动 |
| `src/models.py` | 配置模型兼容现有格式 |
| `core_principles/*` | 系统原则禁止修改 |
| `auto/自主探索 SOP.md` | SOP 内容保持不变 |

---

## 七、实现路径

### 7.1 分阶段实施

```
Phase 1 (Week 1-2): AutonomousExplorer 增强
├── completion_promise 检测
├── 配置参数解析
└── 防无限循环上限
│
Phase 2 (Week 3-4): RalphLoop 核心实现
├── RalphLoop 类
├── 完成验证机制
├── 上下文重置逻辑
└── 状态持久化
│
Phase 3 (Week 5): 工具与集成
├── ralph_tools.py
├── scheduler 集成
├── CLI 命令支持
│
Phase 4 (Week 6): 测试与文档
├── 单元测试
├── 集成测试
└── 使用文档
```

### 7.2 关键接口设计

```python
# 启动 Ralph Loop 的入口
async def create_ralph_loop(
    agent: AgentLoop,
    task_file: str,
    completion: CompletionType,
    criteria: dict
) -> RalphLoop:
    """创建 Ralph Loop 实例"""

# 从 AutonomousExplorer 触发
class AutonomousExplorer:
    async def _maybe_start_ralph(self, todo_item: dict):
        """判断 TODO 是否需要 Ralph Loop"""
        if todo_item.get("requires_ralph"):
            ralph = await create_ralph_loop(...)
            return await ralph.run()
```

---

## 八、测试验证方案

### 8.1 测试用例设计

| 测试类别 | 用例 | 验证点 |
|----------|------|--------|
| **completion_promise** | 写入 DONE 标志 | Loop 正确退出 |
| **上下文重置** | 迭代5轮后 | history 被清空，prompt 重新注入 |
| **安全上限** | 达到1000次迭代 | 强制退出，生成报告 |
| **状态恢复** | 模拟进程崩溃 | 重启后从 iteration=N 继续 |
| **测试验证** | pytest 失败→成功 | test_pass 检测生效 |

### 8.2 集成测试场景

```python
# tests/integration/test_ralph_flow.py

async def test_ralph_loop_marker_completion():
    """测试 marker_file 完成验证"""
    # 1. 创建任务文件
    task_file = create_task_file("实现用户认证模块")
    
    # 2. 启动 Ralph Loop
    ralph = RalphLoop(
        agent=test_agent,
        completion_type=CompletionType.MARKER_FILE,
        completion_criteria={"marker_path": ".seed/done"},
        task_prompt_path=task_file
    )
    
    # 3. 模拟 Agent 执行
    # 4. 写入完成标志
    Path(".seed/done").write_text("DONE")
    
    # 5. 验证 Ralph Loop 退出
    result = await ralph.run()
    assert result == "DONE"

async def test_ralph_loop_context_reset():
    """测试上下文重置"""
    ralph = RalphLoop(..., context_reset_interval=3)
    
    # 执行3轮迭代
    for i in range(3):
        await ralph.run_single_iteration()
    
    # 验证 history 被重置
    assert len(ralph.agent.history) <= 2  # system + user
```

---

## 九、风险与缓解

### 9.1 风险矩阵

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **无限循环** | 资源耗尽 | 中 | 硬上限 + 时间限制 |
| **上下文丢失关键信息** | 任务偏离 | 低 | 保留摘要 + 状态文件 |
| **完成验证误判** | 过早退出 | 低 | 多重验证 + 人工确认选项 |
| **状态文件损坏** | 无法恢复 | 低 | JSON 校验 + 备份 |
| **与 TaskScheduler 冲突** | 双重执行 | 中 | 任务去重机制 |

### 9.2 安全机制清单

```
✓ 迭代上限: 1000 次
✓ 时间上限: 8 小时
✓ 完成标志文件: 必须精确匹配
✓ 状态文件: JSON 格式校验
✓ 任务去重: 检查 scheduler 已执行任务
✓ 进程隔离: Ralph Loop 可独立进程运行
```

---

## 十、使用示例

### 10.1 通过工具调用启动

```python
# Agent 在自主模式下执行
await start_ralph_loop(
    task_prompt_file=".seed/tasks/refactor_auth.md",
    completion_type="test_pass",
    max_iterations=500
)

# 任务完成后写入标志
await write_completion_marker("DONE")
```

### 10.2 CLI 命令启动

```bash
# 启动 Ralph Loop
python main.py --ralph-loop --task .seed/tasks/refactor.md --completion test_pass

# 检查状态
python main.py --ralph-status
```

### 10.3 在 AutonomousExplorer 中触发

当 TODO 条目标记 `requires_ralph: true` 时：

```markdown
TODO.md:
- [x] 完成用户模块基础功能
- [ ] 重构认证系统 | 验收: 测试通过率100% | requires_ralph: true
```

AutonomousExplorer 自动判断并启动 Ralph Loop。

---

## 十一、后续演进方向

### 11.1 短期优化

- 多 Ralph Loop 并行执行
- 进度可视化（Web UI）
- 完成条件组合（test_pass + git_clean）

### 11.2 长期演进

- 跨模型审查（执行模型 + 审查模型）
- Specify-Lisa-Ralph 三阶段模式
- Ralph Loop 编排器（多任务队列）

---

## 附录

### A. 参考文档

- `docs/ralph_loop.md` - Ralph Loop 概念起源
- `src/agent_loop.py` - 现有 Agent Loop 实现
- `src/autonomous.py` - 现有 Autonomous Explorer 实现
- `memory/memory.md` - 记忆层次结构

### B. 术语表

| 术语 | 定义 |
|------|------|
| **Agent Loop** | 单次对话执行循环，迭代上限30 |
| **Ralph Loop** | 外部验证驱动的长周期循环 |
| **completion_promise** | 完成标志文件/令牌 |
| **context reset** | 清空 history 重新注入 prompt |
| **state persistence** | 迭代状态保存于文件系统 |

---

> **文档版本**: v1.0
> **创建日期**: 2026-04-19
> **作者**: Sisyphus (AI Agent)
> **状态**: 设计草案，待实施评审