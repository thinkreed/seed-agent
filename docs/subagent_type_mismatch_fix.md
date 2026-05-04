# Subagent 类型不匹配错误修复方案

## 落地记录

**落地日期**: 2026-05-04
**落地状态**: ✅ 已完成

### 实际修改文件

| 文件 | 修改内容 | 状态 |
|------|----------|------|
| `src/tools/subagent_tools.py` | 添加 `_safe_int_convert()` 辅助函数，修改 `spawn_subagent`, `spawn_parallel_subagents`, `wait_for_subagent_async`, `aggregate_subagent_results` 函数 | ✅ |
| `src/subagent_manager.py` | 添加 `_safe_int()` 辅助函数，为 `SubagentTask` 添加 `__post_init__` 类型验证 | ✅ |
| `src/tools/builtin_tools.py` | 修改 `file_read`, `code_as_policy`, `code_as_policy_async` 函数添加类型转换 | ✅ |
| `src/tools/ralph_tools.py` | 添加 `_safe_int_convert()` 辅助函数，修改 `start_ralph_loop` 函数 | ✅ |
| `tests/test_subagent.py` | 添加 `TestTypeSafetyConversion` 和 `TestSubagentTaskTypeSafety` 测试类 | ✅ |

### 测试覆盖

新增测试用例：
- `test_safe_int_convert_valid_string` - 有效字符串转换
- `test_safe_int_convert_valid_int` - 整数直接返回
- `test_safe_int_convert_invalid_string` - 无效字符串返回默认值
- `test_safe_int_convert_none` - None 返回默认值
- `test_safe_int_convert_negative` - 负数返回默认值
- `test_safe_int_convert_zero` - 零返回默认值（min_val=1）
- `test_safe_int_convert_zero_allowed` - 零允许（min_val=0）
- `test_spawn_subagent_with_string_timeout` - spawn_subagent 接收字符串 timeout
- `test_spawn_subagent_with_invalid_timeout` - spawn_subagent 接收无效 timeout
- `test_spawn_subagent_with_negative_timeout` - spawn_subagent 接收负数 timeout
- `test_spawn_parallel_subagents_with_string_timeout` - spawn_parallel_subagents 接收字符串 timeout
- `test_spawn_parallel_subagents_with_invalid_timeout` - spawn_parallel_subagents 接收无效 timeout
- `test_aggregate_subagent_results_with_string_max_length` - aggregate 接收字符串 max_length
- `test_aggregate_subagent_results_with_invalid_max_length` - aggregate 接收无效 max_length
- `test_subagent_task_string_timeout_conversion` - SubagentTask 字符串 timeout 自动转换
- `test_subagent_task_invalid_timeout_conversion` - SubagentTask 无效 timeout 处理
- `test_subagent_task_negative_timeout_conversion` - SubagentTask 负数 timeout 处理
- `test_subagent_task_string_max_iterations_conversion` - SubagentTask 字符串 max_iterations 自动转换
- `test_subagent_task_string_priority_conversion` - SubagentTask 字符串 priority 自动转换
- `test_subagent_task_negative_priority_conversion` - SubagentTask 负数 priority 处理

---

## 问题概述

**错误现象**:
```
2026-05-04 08:40:53,190 | ERROR | Subagent de9a15a5 failed: '<=' not supported between instances of 'str' and 'int'
RuntimeWarning: coroutine 'SubagentInstance._run_loop' was never awaited
```

**触发场景**: 调用 `spawn_parallel_subagents` 工具时，多个 Subagent 任务同时失败。

---

## 问题根源分析

### 根因链路追踪

```
LLM Function Calling → JSON 参数 → parse_tool_arguments → 工具函数 → SubagentTask → SubagentInstance → asyncio.wait_for → 类型比较失败
```

### 详细分析

#### 1. 参数解析无类型转换 (`src/tools/utils.py`)

```python
def parse_tool_arguments(raw_args: str | dict | None) -> dict[str, Any]:
    """解析工具参数"""
    ...
    parsed = json.loads(raw_args)  # 直接解析，不做类型转换
    if isinstance(parsed, dict):
        return parsed  # 返回原始类型，可能包含字符串类型的数值
```

**问题**: 当 LLM 返回 `"timeout": "300"` (JSON 字符串) 时，解析后仍是 Python 字符串 `"300"`，而不是整数 `300`。

#### 2. 工具函数类型注解仅作提示 (`src/tools/subagent_tools.py`)

```python
def spawn_subagent(
    type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,  # ← 类型注解仅作提示，不强制转换
) -> str:
    ...
    task_id = _subagent_manager.create_task(
        subagent_type=subagent_type,
        prompt=prompt,
        timeout=timeout,  # ← 可能传入字符串
    )
```

```python
def spawn_parallel_subagents(tasks: list[dict]) -> str:
    ...
    for task_spec in tasks:
        task_id = _subagent_manager.create_task(
            subagent_type=subagent_type,
            prompt=task_spec.get("prompt", ""),
            timeout=task_spec.get("timeout", 300),  # ← 如果 key 存在但值是字符串，不使用默认值
        )
```

**问题**: `dict.get(key, default)` 如果 key 存在，返回实际值（可能是字符串），不使用默认值。

#### 3. Dataclass 无类型验证 (`src/subagent_manager.py`)

```python
@dataclass
class SubagentTask:
    id: str
    subagent_type: SubagentType
    prompt: str
    timeout: int | None = None  # ← 类型注解不强制，实际可能存储字符串
    priority: int = 0           # ← 同样问题
```

**问题**: Python dataclass 类型注解仅作文档提示，不会自动转换或验证类型。

#### 4. 类型错误触发点 (`asyncio.wait_for` 内部)

```python
# SubagentInstance.run() (src/subagent.py:387)
result = await asyncio.wait_for(self._run_loop(), timeout=self.timeout)

# asyncio.wait_for 内部实现 (Python 标准库)
def wait_for(aw, timeout):
    if timeout is None:
        ...
    if timeout <= 0:  # ← 这里触发错误！字符串 "300" 与整数 0 比较
        ...
```

**问题**: `asyncio.wait_for` 在检查 `timeout <= 0` 时，字符串 `"300"` 与整数 `0` 比较报错：
```
TypeError: '<=' not supported between instances of 'str' and 'int'
```

#### 5. Coroutine 未 await 原因

当 `asyncio.wait_for` 在类型检查阶段（执行 coroutine 之前）抛出异常时，`_run_loop()` 创建的 coroutine 从未被 await，触发 RuntimeWarning：

```python
async def run(self, prompt, task_id):
    ...
    try:
        # 1. 创建 coroutine: self._run_loop()
        # 2. asyncio.wait_for 内部检查 timeout <= 0
        # 3. 类型错误立即抛出，coroutine 未 await
        result = await asyncio.wait_for(self._run_loop(), timeout=self.timeout)
    except asyncio.TimeoutError:
        ...
```

---

## 影响范围

所有接收数值参数的工具都可能受此影响：

| 工具 | 数值参数 | 风险 |
|------|----------|------|
| `spawn_subagent` | `timeout` | **高** - 直接传给 asyncio |
| `spawn_parallel_subagents` | `timeout` | **高** - 直接传给 asyncio |
| `aggregate_subagent_results` | `max_length` | **中** - 比较操作 |
| `file_read` | `start`, `count` | **低** - 内部转换 |
| `code_as_policy` | `timeout` | **中** - subprocess 参数 |

---

## 修复方案

### 方案 A: 工具函数入口类型强制转换 (推荐)

**修改位置**: `src/tools/subagent_tools.py`

**优点**:
- 修复在最上层，阻止错误传播
- 不影响现有 dataclass 和类结构
- 改动最小，风险最低

**修改示例**:

```python
def spawn_subagent(
    type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,
) -> str:
    """创建并启动一个子代理任务"""
    
    # === 新增: 类型强制转换 ===
    if timeout is not None:
        try:
            timeout = int(timeout) if isinstance(timeout, str) else timeout
            if timeout <= 0:
                return "Error: timeout must be positive"
        except (ValueError, TypeError):
            return "Error: timeout must be a valid integer"
    
    ...
    task_id = _subagent_manager.create_task(
        subagent_type=subagent_type,
        prompt=prompt,
        timeout=timeout,  # ← 现在是整数
    )
```

```python
def spawn_parallel_subagents(tasks: list[dict]) -> str:
    """创建并并行启动多个子代理任务"""
    
    task_ids = []
    for task_spec in tasks:
        # === 新增: 类型强制转换 ===
        raw_timeout = task_spec.get("timeout", 300)
        try:
            timeout = int(raw_timeout) if isinstance(raw_timeout, str) else raw_timeout
            if timeout <= 0:
                timeout = 300  # 使用默认值
        except (ValueError, TypeError):
            timeout = 300  # 使用默认值
        
        task_id = _subagent_manager.create_task(
            subagent_type=subagent_type,
            prompt=task_spec.get("prompt", ""),
            timeout=timeout,  # ← 现在是整数
        )
```

```python
def aggregate_subagent_results(
    task_ids: list[str],
    include_errors: bool = True,
    max_length: int = 2000,
) -> str:
    """聚合多个子代理的执行结果"""
    
    # === 新增: 类型强制转换 ===
    try:
        max_length = int(max_length) if isinstance(max_length, str) else max_length
        if max_length <= 0:
            max_length = 2000  # 使用默认值
    except (ValueError, TypeError):
        max_length = 2000
    
    return _subagent_manager.aggregate_results(
        task_ids=task_ids,
        include_errors=include_errors,
        max_length=max_length,  # ← 现在是整数
    )
```

---

### 方案 B: Dataclass `__post_init__` 类型验证

**修改位置**: `src/subagent_manager.py`

**优点**:
- 在数据结构层面保证类型正确
- 所有使用 SubagentTask 的地方都受益

**修改示例**:

```python
@dataclass
class SubagentTask:
    """Subagent 任务定义"""
    
    id: str
    subagent_type: SubagentType
    prompt: str
    custom_tools: set[str] | None = None
    custom_system_prompt: str | None = None
    max_iterations: int | None = None
    timeout: int | None = None
    priority: int = 0
    
    def __post_init__(self):
        """创建后类型验证和转换"""
        # 强制转换 timeout
        if self.timeout is not None and isinstance(self.timeout, str):
            try:
                self.timeout = int(self.timeout)
            except ValueError:
                logger.warning(f"Invalid timeout value: {self.timeout}, using None")
                self.timeout = None
        
        # 强制转换 max_iterations
        if self.max_iterations is not None and isinstance(self.max_iterations, str):
            try:
                self.max_iterations = int(self.max_iterations)
            except ValueError:
                logger.warning(f"Invalid max_iterations: {self.max_iterations}, using None")
                self.max_iterations = None
        
        # 强制转换 priority
        if isinstance(self.priority, str):
            try:
                self.priority = int(self.priority)
            except ValueError:
                logger.warning(f"Invalid priority value: {self.priority}, using 0")
                self.priority = 0
        
        # 验证范围
        if self.timeout is not None and self.timeout <= 0:
            logger.warning(f"Invalid timeout: {self.timeout} <= 0, using None")
            self.timeout = None
        
        if self.max_iterations is not None and self.max_iterations <= 0:
            logger.warning(f"Invalid max_iterations: {self.max_iterations} <= 0, using None")
            self.max_iterations = None
```

---

### 方案 C: Pydantic 参数模型验证

**修改位置**: `src/tools/subagent_tools.py` (新增模型)

**优点**:
- 自动类型转换和验证
- 更好的错误消息
- 符合现代 Python 最佳实践

**修改示例**:

```python
from pydantic import BaseModel, Field, field_validator

class SubagentTaskSpec(BaseModel):
    """Subagent 任务参数模型"""
    
    type: str = Field(..., pattern="^(explore|review|implement|plan)$")
    prompt: str = Field(..., min_length=1)
    timeout: int | None = Field(default=300, ge=1, le=3600)
    
    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v
    
    @field_validator('timeout', mode='before')
    @classmethod
    def convert_timeout(cls, v):
        if v is None:
            return 300
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return 300  # 默认值
        return v

class SpawnSubagentParams(BaseModel):
    """spawn_subagent 参数模型"""
    
    type: str = Field(..., pattern="^(explore|review|implement|plan)$")
    prompt: str = Field(..., min_length=1)
    custom_tools: list[str] | None = None
    timeout: int | None = Field(default=None, ge=1, le=3600)
    
    @field_validator('timeout', mode='before')
    @classmethod
    def convert_timeout(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                raise ValueError(f"Invalid timeout: {v}")
        return v
```

```python
def spawn_subagent(
    type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,
) -> str:
    """创建并启动一个子代理任务"""
    
    try:
        # Pydantic 验证
        params = SpawnSubagentParams(
            type=type,
            prompt=prompt,
            custom_tools=custom_tools,
            timeout=timeout,
        )
    except ValidationError as e:
        return f"Error: Invalid parameters - {e}"
    
    # 使用验证后的参数
    task_id = _subagent_manager.create_task(
        subagent_type=type_map[params.type],
        prompt=params.prompt,
        custom_tools=set(params.custom_tools) if params.custom_tools else None,
        timeout=params.timeout,
    )
```

---

### 方案 D: SubagentInstance 构造器类型检查

**修改位置**: `src/subagent.py`

**优点**:
- 在最终使用处拦截错误
- 保护 asyncio.wait_for

**修改示例**:

```python
class SubagentInstance:
    def __init__(
        self,
        gateway: LLMGateway,
        subagent_type: SubagentType,
        model_id: str | None = None,
        max_iterations: int = MAX_SUBAGENT_ITERATIONS,
        timeout: int | None = None,
        ...
    ):
        # === 新增: 类型检查和转换 ===
        if timeout is not None:
            if isinstance(timeout, str):
                try:
                    timeout = int(timeout)
                except ValueError:
                    logger.warning(f"Invalid timeout string: {timeout}, using default")
                    timeout = None
            elif not isinstance(timeout, (int, float)):
                logger.warning(f"Invalid timeout type: {type(timeout)}, using default")
                timeout = None
        
        if max_iterations is not None:
            if isinstance(max_iterations, str):
                try:
                    max_iterations = int(max_iterations)
                except ValueError:
                    logger.warning(f"Invalid max_iterations string: {max_iterations}, using default")
                    max_iterations = MAX_SUBAGENT_ITERATIONS
            elif not isinstance(max_iterations, int):
                max_iterations = MAX_SUBAGENT_ITERATIONS
        
        # 验证范围
        if timeout is not None and timeout <= 0:
            logger.warning(f"timeout <= 0: {timeout}, using default")
            timeout = None
        
        if max_iterations <= 0:
            logger.warning(f"max_iterations <= 0: {max_iterations}, using default")
            max_iterations = MAX_SUBAGENT_ITERATIONS
        
        self.timeout = timeout or DEFAULT_TIMEOUTS.get(
            _get_subagent_type_key(subagent_type), 300
        )
        self.max_iterations = max_iterations
        ...
```

---

## 推荐组合方案

**最佳修复策略**: **方案 A + 方案 B** 组合

1. **方案 A** (工具函数入口): 第一道防线，立即转换类型
2. **方案 B** (Dataclass): 第二道防线，确保内部数据结构类型正确

**理由**:
- 方案 A 拦截在最上层，防止无效数据进入系统
- 方案 B 确保即使有遗漏，数据结构也能自我修正
- 不引入 Pydantic 依赖（方案 C）
- 不增加 SubagentInstance 复杂度（方案 D）

---

## 完整修复代码

### 文件 1: `src/tools/subagent_tools.py`

```python
# === 新增辅助函数 ===

def _safe_int_convert(value: Any, default: int, min_val: int = 1) -> int:
    """安全地将值转换为整数
    
    Args:
        value: 要转换的值（可能是 str, int, float, None 等）
        default: 转换失败时的默认值
        min_val: 最小有效值
    
    Returns:
        int: 转换后的整数，或默认值
    """
    if value is None:
        return default
    
    try:
        result = int(value) if isinstance(value, str) else int(value)
        if result < min_val:
            return default
        return result
    except (ValueError, TypeError):
        return default


def spawn_subagent(
    type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,
) -> str:
    """创建并启动一个子代理任务"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"
    
    from src.subagent import SubagentType
    
    # 类型转换
    type_map = {
        "explore": SubagentType.EXPLORE,
        "review": SubagentType.REVIEW,
        "implement": SubagentType.IMPLEMENT,
        "plan": SubagentType.PLAN,
    }
    
    subagent_type = type_map.get(type.lower())
    if subagent_type is None:
        return f"Error: Unknown subagent type '{type}'"
    
    # === 新增: timeout 类型安全转换 ===
    safe_timeout = _safe_int_convert(timeout, default=300, min_val=1) if timeout is not None else None
    
    # 创建任务
    custom_tools_set = set(custom_tools) if custom_tools else None
    task_id = _subagent_manager.create_task(
        subagent_type=subagent_type,
        prompt=prompt,
        custom_tools=custom_tools_set,
        timeout=safe_timeout,
    )
    
    # 启动异步执行
    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run_subagent_async(task_id))
        add_background_task(task)
    except RuntimeError:
        logger.debug(f"No event loop, task {task_id} created but not started")
    
    logger.info(f"Spawned subagent {task_id} (type={type})")
    return f"Subagent task created: {task_id}\nType: {type}\nStatus: pending"


def spawn_parallel_subagents(tasks: list[dict]) -> str:
    """创建并并行启动多个子代理任务"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"
    
    from src.subagent import SubagentType
    
    type_map = {
        "explore": SubagentType.EXPLORE,
        "review": SubagentType.REVIEW,
        "implement": SubagentType.IMPLEMENT,
        "plan": SubagentType.PLAN,
    }
    
    task_ids = []
    for task_spec in tasks:
        type_str = task_spec.get("type", "explore").lower()
        subagent_type = type_map.get(type_str)
        if subagent_type is None:
            return f"Error: Unknown type '{type_str}' in task spec"
        
        # === 新增: timeout 类型安全转换 ===
        raw_timeout = task_spec.get("timeout")
        safe_timeout = _safe_int_convert(raw_timeout, default=300, min_val=1)
        
        task_id = _subagent_manager.create_task(
            subagent_type=subagent_type,
            prompt=task_spec.get("prompt", ""),
            timeout=safe_timeout,
        )
        task_ids.append(task_id)
    
    # 并行启动
    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run_parallel_async(task_ids))
        add_background_task(task)
    except RuntimeError:
        logger.debug(f"No event loop, {len(task_ids)} tasks created but not started")
    
    return f"Created {len(task_ids)} subagent tasks:\n" + "\n".join(task_ids)


def aggregate_subagent_results(
    task_ids: list[str],
    include_errors: bool = True,
    max_length: int = 2000,
) -> str:
    """聚合多个子代理的执行结果"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"
    
    # === 新增: max_length 类型安全转换 ===
    safe_max_length = _safe_int_convert(max_length, default=2000, min_val=1)
    
    return _subagent_manager.aggregate_results(
        task_ids=task_ids,
        include_errors=include_errors,
        max_length=safe_max_length,
    )
```

### 文件 2: `src/subagent_manager.py`

```python
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _safe_int(value, default=None, min_val=1):
    """安全转换整数"""
    if value is None:
        return default
    try:
        result = int(value)
        if result < min_val:
            return default
        return result
    except (ValueError, TypeError):
        return default


@dataclass
class SubagentTask:
    """Subagent 任务定义"""
    
    id: str
    subagent_type: SubagentType
    prompt: str
    custom_tools: set[str] | None = None
    custom_system_prompt: str | None = None
    max_iterations: int | None = None
    timeout: int | None = None
    priority: int = 0
    
    def __post_init__(self):
        """创建后类型验证和转换"""
        # timeout 转换
        if self.timeout is not None:
            self.timeout = _safe_int(self.timeout, default=None, min_val=1)
        
        # max_iterations 转换
        if self.max_iterations is not None:
            self.max_iterations = _safe_int(self.max_iterations, default=None, min_val=1)
        
        # priority 转换
        self.priority = _safe_int(self.priority, default=0, min_val=0)
```

---

## 测试验证方案

### 单元测试

```python
import pytest
from src.tools.subagent_tools import spawn_subagent, _safe_int_convert

def test_safe_int_convert():
    """测试类型转换函数"""
    assert _safe_int_convert("300", 100) == 300
    assert _safe_int_convert(300, 100) == 300
    assert _safe_int_convert("abc", 100) == 100  # 无效字符串 -> 默认值
    assert _safe_int_convert(None, 100) == 100   # None -> 默认值
    assert _safe_int_convert("-5", 100) == 100   # 负数 -> 默认值
    assert _safe_int_convert("0", 100, min_val=1) == 100  # 0 -> 默认值

def test_spawn_subagent_with_string_timeout():
    """测试字符串 timeout 参数"""
    result = spawn_subagent(
        type="explore",
        prompt="Test prompt",
        timeout="60",  # 字符串 timeout
    )
    assert "Error" not in result
    assert "task created" in result.lower()

def test_spawn_subagent_with_invalid_timeout():
    """测试无效 timeout 参数"""
    result = spawn_subagent(
        type="explore",
        prompt="Test prompt",
        timeout="invalid",  # 无效字符串
    )
    # 应使用默认值，不报错
    assert "task created" in result.lower()
```

### 集成测试

```python
async def test_subagent_execution_with_string_timeout():
    """测试完整执行链路"""
    manager = SubagentManager(gateway)
    
    task_id = manager.create_task(
        subagent_type=SubagentType.EXPLORE,
        prompt="Test",
        timeout="120",  # 字符串 timeout
    )
    
    result = await manager.run_subagent(task_id)
    assert result.state.status in ("completed", "failed")
    # 不应出现类型错误
    if result.error:
        assert "'<=' not supported" not in result.error
```

---

## 相关问题修复

### 其他可能受影响的工具

| 文件 | 工具 | 参数 | 修复方法 |
|------|------|------|----------|
| `builtin_tools.py` | `file_read` | `start`, `count` | 内部已有 `int()` 转换，无需修复 |
| `builtin_tools.py` | `code_as_policy` | `timeout` | 需添加类型转换 |
| `ralph_tools.py` | `start_ralph_loop` | `max_iterations` | 需添加类型转换 |

### `code_as_policy` 修复示例

```python
def code_as_policy(
    code: str,
    language: str = "python",
    cwd: str = None,
    timeout: int = 60,
) -> str:
    """执行代码"""
    
    # 类型转换
    try:
        timeout = int(timeout) if isinstance(timeout, str) else timeout
        if timeout <= 0:
            timeout = 60
    except (ValueError, TypeError):
        timeout = 60
    
    ...
```

---

## 总结

| 项目 | 内容 |
|------|------|
| **根因** | LLM 返回字符串数值参数，工具函数未做类型转换 |
| **触发点** | `asyncio.wait_for` 内部 `timeout <= 0` 比较 |
| **副作用** | `_run_loop()` coroutine 未 await，产生 RuntimeWarning |
| **修复方案** | 工具函数入口 + Dataclass `__post_init__` 双层防御 |
| **修改文件** | `src/tools/subagent_tools.py`, `src/subagent_manager.py` |
| **风险等级** | 低 - 仅增加类型转换逻辑，不影响核心流程 |

---

## 附录: asyncio.wait_for 源码分析

```python
# Python 3.10+ asyncio/tasks.py

async def wait_for(fut, timeout):
    """Wait for the single Future or coroutine to complete, with timeout."""
    
    if timeout is None:
        return await fut
    
    # === 类型检查点 ===
    if timeout <= 0:  # ← 字符串与整数比较报错
        timeout_msg = "" if timeout > 0 else f"{timeout} <= 0"
        raise asyncio.TimeoutError(timeout_msg)
    
    ...
```

当 `timeout` 为字符串 `"300"` 时：
1. `timeout is None` → False (字符串不是 None)
2. `timeout <= 0` → TypeError: `'<=' not supported between instances of 'str' and 'int'`
3. 异常在 coroutine await 之前抛出
4. `fut` (即 `_run_loop()` coroutine) 从未 await
5. Python 产生 RuntimeWarning

---

*文档生成时间: 2026-05-04*
*问题发现者: 用户报告*
*分析者: Sisyphus Agent*