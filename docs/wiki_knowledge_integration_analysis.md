# Wiki 知识落地分析报告

## 日期: 2026-05-06

## 概述

基于 E:\projects\wiki 目录下五个开源项目的架构分析，提取可落地的优化点并评估适用性。

---

## 一、已实现的优化点（seed-agent 已具备）

| 来源 | 优化点 | seed-agent 实现 | 状态 |
|------|--------|-----------------|------|
| qwen-code | 三件套解耦架构 | LLMClient + Harness + Sandbox | ✅ 已实现 |
| qwen-code | AbortSignal 取消机制 | `src/abort_signal.py` + `_cancellation_token` | ✅ 已实现 |
| qwen-code | Ask User 等待机制 | `src/tools/ask_user_types.py` | ✅ 已实现 |
| qwen-code | BackgroundTaskRegistry | `src/background_task_registry.py` | ✅ 已实现 |
| qwen-code | LifecycleHooks | `src/lifecycle_hooks/` 模块拆分 | ✅ 已实现 |
| open-agents | Subagent 上下文隔离 | `src/subagent.py` | ✅ 已实现 |
| open-agents | Subagent 类型分级 | EXPLORE/REVIEW/IMPLEMENT/PLAN | ✅ 已实现 |
| hermes | SQLite+FTS5 会话存储 | `src/tools/session_db.py` | ✅ 已实现 |
| hermes | 工具注册表模式 | `src/tools/__init__.py` ToolRegistry | ✅ 已实现 |
| genericagent | 自主探索空闲检测 | `src/autonomous/_idle_monitor.py` | ✅ 已实现 |
| mia | MPE 三代理架构 | SubagentManager + Planner/Executor 分工 | ✅ 部分实现 |
| mia | 混合评分检索 | SessionDB FTS5 + 相关性计算 | ✅ 部分实现 |

---

## 二、需要增强的优化点（已有基础，需升级）

### 2.1 工具系统增强

| 来源 | 优化点 | 当前状态 | 增强建议 |
|------|--------|----------|----------|
| qwen-code | DeclarativeTool 模式 | 参数验证与执行耦合 | 分离 validateToolParams 与 execute |
| qwen-code | Kind 枚举分类 | 无工具分类 | 添加 Read/Edit/Delete/Execute/Search 分类 |
| qwen-code | 三级权限模式 | 部分实现 | 完善 allow/ask/deny 权限判定 |
| hermes | 并行工具执行 | 无 | 添加 CONCURRENCY_SAFE_KINDS 判断 |

**增强代码示例**:
```python
# src/tools/_kinds.py
from enum import Enum

class ToolKind(Enum):
    READ = "read"      # 固有安全
    EDIT = "edit"      # 需确认
    DELETE = "delete"  # 高风险
    MOVE = "move"      # 需确认
    SEARCH = "search"  # 固有安全
    EXECUTE = "execute" # 需确认
    THINK = "think"    # 固有安全
    FETCH = "fetch"    # 固有安全
    OTHER = "other"    # 需评估

MUTATOR_KINDS = frozenset({ToolKind.EDIT, ToolKind.DELETE, ToolKind.MOVE, ToolKind.EXECUTE})
CONCURRENCY_SAFE_KINDS = frozenset({ToolKind.READ, ToolKind.SEARCH, ToolKind.FETCH, ToolKind.THINK})
```

### 2.2 记忆系统增强

| 来源 | 优化点 | 当前状态 | 增强建议 |
|------|--------|----------|----------|
| mia | win_rate 字段 | 无 | 为记忆条目添加成功率追踪 |
| mia | 记忆去重机制 | 无 | 相似度 ≥ 0.9999 时触发更新逻辑 |
| genericagent | 行动验证原则 | 部分实现 | 只有成功执行才能写入 L1/L2/L3 |
| qwen-code | 整合锁机制 | 无 | 文件锁防止并发 Dream |
| qwen-code | 提取光标 | 无 | extract-cursor.json 避免重复处理 |

**增强代码示例**:
```python
# src/tools/memory/_win_rate.py
from dataclasses import dataclass

@dataclass
class MemoryEntry:
    content: str
    usage_count: int = 0
    success_count: int = 0
    win_rate: float = 0.5
    
    def update_success(self, success: bool):
        self.usage_count += 1
        if success:
            self.success_count += 1
        self.win_rate = self.success_count / self.usage_count

# 混合评分检索
def retrieve_with_win_rate(query_embedding, entries, top_k=5):
    similarities = cosine_similarity(query_embedding, [e.embedding for e in entries])
    win_rates = [e.win_rate for e in entries]
    combined = 0.7 * normalize(similarities) + 0.3 * win_rates
    return sorted(zip(entries, combined), key=lambda x: x[1], reverse=True)[:top_k]
```

### 2.3 Hooks 系统增强

| 来源 | 优化点 | 当前状态 | 增强建议 |
|------|--------|----------|----------|
| qwen-code | MessageBus.request() | 无请求/响应模式 | 添加 AbortSignal 支持的请求/响应 |
| qwen-code | HookAggregator | 无结果合并 | 多 Hook 结果合并，deny 优先 |
| qwen-code | SSRF 防护 | 无 | HTTP Hook DNS 验证，禁止私有地址 |

**增强代码示例**:
```python
# src/lifecycle_hooks/_message_bus.py
import asyncio
from typing import Dict, Any, Optional
import uuid

class MessageBus:
    def __init__(self):
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    async def request(
        self,
        request_type: str,
        payload: Dict[str, Any],
        timeout_ms: int = 60000,
        signal: Optional[AbortSignal] = None
    ) -> Dict[str, Any]:
        correlation_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[correlation_id] = future
        
        def on_abort():
            if not future.done():
                future.cancel()
                self._pending_requests.pop(correlation_id, None)
        
        if signal:
            signal.add_listener(on_abort)
        
        self._emit(request_type, {**payload, "correlation_id": correlation_id})
        
        try:
            return await asyncio.wait_for(future, timeout=timeout_ms / 1000)
        except asyncio.TimeoutError:
            self._pending_requests.pop(correlation_id, None)
            raise TimeoutError("Request timeout")
        finally:
            if signal:
                signal.remove_listener(on_abort)
```

---

## 三、需要新增的优化点（完全缺失）

### 3.1 核心引擎新增

| 来源 | 优化点 | 价值 | 实现建议 |
|------|--------|------|----------|
| qwen-code | LoopDetectionService | 防止无限循环 | 检测重复工具调用模式 |
| qwen-code | 双重历史管理 | API 发送有效轮次 | curated_history 过滤无效对话 |
| genericagent | StepOutcome 统一返回 | 工具结果标准化 | (data, next_prompt, should_exit) 三元组 |

**新增代码示例**:
```python
# src/harness/_loop_detection.py
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class LoopPattern:
    tool_sequence: Tuple[str, ...]
    count: int
    last_seen_at: int

class LoopDetectionService:
    def __init__(self, max_repeats: int = 3, window_size: int = 10):
        self._patterns: defaultdict = defaultdict(LoopPattern)
        self._max_repeats = max_repeats
        self._window_size = window_size
    
    def check(self, recent_calls: List[str]) -> Tuple[bool, str]:
        """检测是否陷入循环"""
        if len(recent_calls) < self._window_size:
            return False, ""
        
        # 检查最近 window_size 次调用中的重复模式
        for pattern_len in range(2, self._window_size // 2):
            patterns = self._extract_patterns(recent_calls, pattern_len)
            for pattern, count in patterns.items():
                if count >= self._max_repeats:
                    return True, f"Loop detected: {pattern} repeated {count} times"
        
        return False, ""
```

### 3.2 Skills 系统新增

| 来源 | 优化点 | 价值 | 实现建议 |
|------|--------|------|----------|
| hermes | 渐进式披露 | 减少上下文膨胀 | skills_list 仅元数据、skill_view 加载内容 |
| hermes | 项目级优先 | 项目覆盖用户配置 | projectSkillsDirs 先扫描 |
| open-agents | Claude 兼容转换 | 扩展生态复用 | plugin.json → skill 转换 |

**新增代码示例**:
```python
# src/tools/skill_loader/_progressive_disclosure.py

# skills_list 仅返回元数据
def list_skills_metadata() -> List[SkillMetadata]:
    """返回所有技能的元数据列表（不加载完整内容）"""
    skills = []
    seen_names = set()
    
    # 项目级优先（先扫描）
    for project_dir in get_project_skill_dirs():
        for skill_file in project_dir.glob("SKILL.md"):
            metadata = parse_frontmatter(skill_file)
            if metadata.name not in seen_names:
                skills.append(metadata)
                seen_names.add(metadata.name)
    
    # 用户级（后扫描，去重）
    user_dir = get_user_skill_dir()
    for skill_file in user_dir.glob("SKILL.md"):
        metadata = parse_frontmatter(skill_file)
        if metadata.name not in seen_names:
            skills.append(metadata)
            seen_names.add(metadata.name)
    
    return skills

# skill_view 按需加载完整内容
def load_skill_content(skill_name: str) -> str:
    """按需加载指定技能的完整内容"""
    skill_path = find_skill_path(skill_name)
    if skill_path:
        return skill_path.read_text(encoding="utf-8")
    return ""
```

### 3.3 Provider 抽象新增

| 来源 | 优化点 | 价值 | 实现建议 |
|------|--------|------|----------|
| hermes | OAuth 设备码流程 | 无 API Key Provider 支持 | 自动刷新 Token |
| hermes | Credential Pool | 多 Key 负载均衡 | 凭证轮换策略 |

---

## 四、实施优先级

### P0 - 立即落地（高价值 + 低复杂度）

| 优化点 | 文件 | 预估工作量 |
|------|------|-----------|
| ToolKind 枚举分类 | `src/tools/_kinds.py` | 新增文件 |
| LoopDetectionService | `src/harness/_loop_detection.py` | 新增模块 |
| 整合锁机制 | `src/tools/memory/_dream_lock.py` | 新增函数 |
| win_rate 字段 | `src/tools/session_db.py` | 表结构扩展 |

### P1 - 近期优化（高价值 + 中等复杂度）

| 优化点 | 文件 | 预估工作量 |
|------|------|-----------|
| 渐进式披露 Skills | `src/tools/skill_loader/` | 重构现有模块 |
| MessageBus.request() | `src/lifecycle_hooks/_message_bus.py` | 新增模块 |
| DeclarativeTool 模式 | `src/tools/builtin/` | 重构工具定义 |
| 双重历史管理 | `src/session_event_stream.py` | 新增 curated_history |

### P2 - 中期规划（中价值 + 高复杂度）

| 优化点 | 文件 | 预估工作量 |
|------|------|-----------|
| 并行工具执行 | `src/harness/_tool_router.py` | 重构执行逻辑 |
| StepOutcome 统一返回 | `src/tools/__init__.py` | 全工具接口变更 |
| SSRF 防护 | `src/lifecycle_hooks/` | 安全模块扩展 |
| OAuth 设备码流程 | `src/client/` | 新增认证流程 |

---

## 五、落地进度追踪

| 日期 | 已落地 | 待落地 |
|------|--------|--------|
| 2026-05-06 | 开始整合 | P0 全部 |

---

## 六、参考资料

- genericagent: `E:\projects\wiki\genericagent\`
- hermes-agent: `E:\projects\wiki\hermes-agent\`
- mia: `E:\projects\wiki\mia\`
- open-agents: `E:\projects\wiki\open-agents\`
- qwen-code-architecture: `E:\projects\wiki\qwen-code-architecture\`