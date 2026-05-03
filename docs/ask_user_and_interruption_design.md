# Seed-Agent Ask User 与任务打断机制设计文档

## 文档概述

本文档基于 qwen-code 的实现分析，为 seed-agent 设计完整的用户交互（ask user）和任务打断（task interruption）机制。

**设计目标**：
- 实现真正的用户交互等待机制（而非当前的字符串标记）
- 支持任务执行中的打断和取消
- 保持与 seed-agent 现有架构的兼容性
- 提供优雅的清理和状态恢复

---

## 第一部分：现状分析

### 1.1 seed-agent 现有实现

#### 当前 ask_user 工具

**文件**: `src/tools/builtin_tools.py` (lines 525-540)

```python
def ask_user(question: str, options: list | None = None) -> str:
    """Ask user for input/confirmation during task execution."""
    result = f"[ASK_USER] {question}"
    if options:
        result += f"\nOptions: {', '.join(options)}"
    result += "\n[Waiting for user response]"
    return result
```

**问题**：
- 仅返回格式化字符串，不实际暂停执行
- 无等待机制，LLM 继续推理
- 无用户响应收集和注入流程
- 无状态持久化

#### 当前执行架构

```
main.py → AgentLoop.stream_run() → Harness.run_conversation()
    → Harness.run_cycle() → LLM调用 → _route_tool_calls()
    → Sandbox.execute_tools() → 返回结果 → 继续循环
```

**关键组件**：
| 组件 | 文件 | 职责 |
|------|------|------|
| AgentLoop | `src/agent_loop.py` | 主执行引擎，历史管理 |
| Harness | `src/harness.py` | 循环驱动，工具路由 |
| Sandbox | `src/sandbox.py` | 隔离执行环境 |
| SessionEventStream | `src/session_event_stream.py` | 事件流存储 |
| LifecycleHooks | `src/lifecycle_hooks.py` | 生命周期钩子 |

#### 已有的钩子点

**HookPoint 枚举**（已定义但未充分利用）：
- `SESSION_PAUSE` / `SESSION_RESUME` - 会话暂停/恢复
- `TOOL_CALL_BEFORE` / `TOOL_CALL_AFTER` - 工具调用前后
- `LLM_CALL_BEFORE` / `LLM_CALL_AFTER` - LLM 调用前后

### 1.2 qwen-code 实现参考

#### 核心机制

| 机制 | qwen-code 实现 | 关键文件 |
|------|---------------|----------|
| ask_user_question | 工具定义 + 确认回调 | `askUserQuestion.ts` |
| 等待用户输入 | awaiting_approval 状态 | `coreToolScheduler.ts` |
| 确认响应处理 | handleConfirmationResponse | `coreToolScheduler.ts` |
| 任务取消 | AbortController + cancel() | `background-tasks.ts` |
| 信号处理 | SIGINT/SIGTERM handlers | `acpAgent.ts` |

#### ask_user_question 工具

```typescript
// qwen-code: askUserQuestion.ts
export interface Question {
  question: string;
  header: string;
  options: QuestionOption[];
  multiSelect?: boolean;
}

// 工具始终需要用户确认 - 绕过 YOLO 自动批准
override async getDefaultPermission(): Promise<PermissionDecision> {
  return 'ask'; // Always ask user
}
```

#### 工具调度状态机

```typescript
// qwen-code: coreToolScheduler.ts
export type WaitingToolCall = {
  status: 'awaiting_approval';
  request: ToolCallRequestInfo;
  confirmationDetails: ToolCallConfirmationDetails;
};

// 状态流转：validating → awaiting_approval → scheduled → executing → success/error/cancelled
```

#### 确认结果类型

```typescript
// qwen-code: tools.ts
export enum ToolConfirmationOutcome {
  ProceedOnce = 'proceed_once',
  ProceedAlways = 'proceed_always',
  Cancel = 'cancel',
}
```

#### 任务取消机制

```typescript
// qwen-code: background-tasks.ts
cancel(agentId: string): void {
  entry.abortController.abort();  // 发送取消信号
  entry.status = 'cancelled';
  // 5秒优雅期 - 让自然完成处理器赢得竞争
  setTimeout(() => this.finalizeCancellationIfPending(agentId), 5000);
}
```

---

## 第二部分：Ask User 机制设计

### 2.1 核心设计理念

**关键洞察**：ask_user 的本质是**暂停执行循环**，等待外部输入，然后**恢复执行**。

采用 **Awaitable Pattern**：
- 工具调用返回"等待标记"
- Harness 检测标记后暂停循环
- 外部（main.py）注入用户响应
- Harness 恢复循环继续执行

### 2.2 数据结构定义

#### Question 数据结构

```python
# src/tools/ask_user_types.py (新文件)

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

class QuestionType(Enum):
    """问题类型"""
    SINGLE_SELECT = "single_select"  # 单选
    MULTI_SELECT = "multi_select"    # 多选
    TEXT_INPUT = "text_input"        # 文本输入
    CONFIRMATION = "confirmation"    # 确认（是/否）

@dataclass
class QuestionOption:
    """选项定义"""
    label: str                       # 选项显示文本
    value: Optional[str] = None      # 选项值（默认等于label）
    description: Optional[str] = None # 选项描述

@dataclass
class Question:
    """问题定义"""
    question: str                    # 问题文本
    header: str                      # 简短标题（<=30字符）
    options: List[QuestionOption]    # 选项列表（2-4个）
    question_type: QuestionType = QuestionType.SINGLE_SELECT
    multi_select: bool = False       # 是否多选
    allow_custom: bool = True        # 是否允许自定义输入
    default: Optional[str] = None    # 默认选项

@dataclass
class UserResponse:
    """用户响应"""
    question_id: str                 # 问题ID（索引）
    selected: List[str]              # 选中的选项值列表
    custom_input: Optional[str] = None  # 自定义输入

@dataclass
class AskUserRequest:
    """Ask User 请求（完整结构）"""
    questions: List[Question]
    session_id: str                  # 会话ID
    request_id: str                  # 请求唯一ID
    created_at: float                # 创建时间戳
    metadata: dict = field(default_factory=dict)

@dataclass
class AskUserResult:
    """Ask User 结果"""
    request_id: str
    responses: List[UserResponse]
    cancelled: bool = False          # 用户取消
    timeout: bool = False            # 超时
```

#### EventType 扩展

```python
# 扩展 src/session_event_stream.py 中的 EventType

class EventType(Enum):
    # ... 现有类型 ...
    
    # 新增：用户交互相关
    USER_QUESTION = "user_question"       # 发起问题
    USER_WAITING = "user_waiting"         # 等待用户响应
    USER_RESPONSE = "user_response"       # 用户响应
    USER_CANCELLED = "user_cancelled"     # 用户取消
```

### 2.3 工具层改造

#### 新 ask_user 实现

```python
# src/tools/builtin_tools.py - 改造

import asyncio
from typing import List, Optional
from .ask_user_types import Question, QuestionOption, QuestionType

# 全局等待状态（由 AgentLoop 管理）
_pending_ask_user_request: Optional[AskUserRequest] = None
_ask_user_response_event: asyncio.Event = asyncio.Event()
_ask_user_response: Optional[AskUserResult] = None

def ask_user(
    question: str,
    options: Optional[List[str]] = None,
    header: Optional[str] = None,
    multi_select: bool = False,
) -> str:
    """
    Ask user for input/confirmation during task execution.
    
    这是同步接口，但会触发异步等待机制。
    
    Args:
        question: 问题文本
        options: 选项列表（可选）
        header: 简短标题（可选，默认从问题截取）
        multi_select: 是否多选
    
    Returns:
        等待标记字符串，实际响应由 Harness 处理
    """
    # 构造 Question 结构
    question_obj = Question(
        question=question,
        header=header or question[:30],
        options=[QuestionOption(label=o) for o in (options or ["Yes", "No"])],
        multi_select=multi_select,
    )
    
    # 构造请求
    request = AskUserRequest(
        questions=[question_obj],
        session_id="",  # 由调用方填充
        request_id=str(uuid.uuid4())[:8],
        created_at=time.time(),
    )
    
    # 设置全局等待状态
    global _pending_ask_user_request, _ask_user_response
    _pending_ask_user_request = request
    _ask_user_response = None
    
    # 返回等待标记
    return f"[AWAITING_USER_INPUT] request_id={request.request_id}\n{question}\nOptions: {', '.join(options or [])}"

def get_pending_ask_user_request() -> Optional[AskUserRequest]:
    """获取当前等待中的 ask_user 请求"""
    return _pending_ask_user_request

def inject_user_response(response: AskUserResult) -> None:
    """注入用户响应（由外部调用）"""
    global _ask_user_response, _pending_ask_user_request, _ask_user_response_event
    _ask_user_response = response
    _pending_ask_user_request = None
    _ask_user_response_event.set()

def clear_ask_user_state() -> None:
    """清理等待状态"""
    global _pending_ask_user_request, _ask_user_response, _ask_user_response_event
    _pending_ask_user_request = None
    _ask_user_response = None
    _ask_user_response_event.clear()
```

### 2.4 Harness 层改造

#### 等待状态检测

```python
# src/harness.py - 改造

class Harness:
    """控制器：驱动循环，路由工具"""
    
    def __init__(self, ...):
        # ... 现有初始化 ...
        self._waiting_for_user: bool = False
        self._user_response: Optional[AskUserResult] = None
    
    async def run_cycle(self, signal: AbortSignal) -> Dict:
        """执行一轮循环
        
        返回值包含等待状态信息
        """
        # 1. 构建上下文
        context = self._build_context_from_session()
        
        # 2. LLM 调用
        response = await self.llm_client.chat_completion(
            messages=context,
            tools=self.tools.get_schemas(),
        )
        
        # 3. 处理响应
        message = response['choices'][0]['message']
        
        # 4. 检查是否有工具调用
        if message.get('tool_calls'):
            # 执行工具
            tool_results = await self._execute_tool_calls(message['tool_calls'])
            
            # **关键：检查是否触发了 ask_user 等待**
            pending_request = get_pending_ask_user_request()
            if pending_request:
                # 发送等待事件到 Session
                self.session.emit_event(
                    EventType.USER_WAITING,
                    {
                        "request": pending_request,
                        "tool_call_id": message['tool_calls'][0]['id'],
                    }
                )
                
                # 设置等待状态并返回
                self._waiting_for_user = True
                return {
                    "status": "waiting_for_user",
                    "request": pending_request,
                    "partial_message": message,
                }
            
            # 正常继续
            self.session.emit_event(EventType.TOOL_RESULT, tool_results)
            return {"status": "continue", "message": message}
        
        # 无工具调用 - 完成
        return {"status": "complete", "message": message}
    
    async def run_conversation(self, signal: AbortSignal) -> str:
        """运行完整对话循环
        
        **改造：支持用户等待恢复**
        """
        iteration = 0
        while iteration < self.max_iterations:
            # 检查取消信号
            if signal.aborted:
                return "[CANCELLED]"
            
            iteration += 1
            result = await self.run_cycle(signal)
            
            # **处理等待状态**
            if result["status"] == "waiting_for_user":
                # 触发 SESSION_PAUSE 钩子
                await self.hooks.trigger(HookPoint.SESSION_PAUSE, {
                    "reason": "user_input_required",
                    "request": result["request"],
                })
                
                # 返回等待状态给调用方（AgentLoop）
                return result
            
            if result["status"] == "complete":
                # 触发 SESSION_END 钩子
                await self.hooks.trigger(HookPoint.SESSION_END, {})
                return result["message"].get("content", "")
        
        raise MaxIterationsExceeded(self.max_iterations)
    
    async def resume_with_user_response(
        self,
        response: AskUserResult,
        signal: AbortSignal
    ) -> str:
        """恢复执行（用户响应后）
        
        Args:
            response: 用户响应数据
            signal: 取消信号
        
        Returns:
            最终响应文本
        """
        # 1. 清理等待状态
        self._waiting_for_user = False
        
        # 2. 记录用户响应事件
        self.session.emit_event(EventType.USER_RESPONSE, {
            "request_id": response.request_id,
            "responses": response.responses,
            "cancelled": response.cancelled,
        })
        
        # 3. 触发 SESSION_RESUME 钩子
        await self.hooks.trigger(HookPoint.SESSION_RESUME, {
            "reason": "user_input_received",
            "response": response,
        })
        
        # 4. 构造工具结果并注入历史
        if response.cancelled:
            tool_result = "[USER_CANCELLED]"
        else:
            # 格式化用户选择
            selected = [r.selected for r in response.responses]
            tool_result = f"User selected: {selected}"
        
        # 5. 注入到历史（作为 tool result）
        # ... 将 tool_result 添加到 session 事件流 ...
        
        # 6. 继续执行循环
        return await self.run_conversation(signal)
```

### 2.5 AgentLoop 层改造

```python
# src/agent_loop.py - 改造

class AgentLoop:
    """主执行引擎"""
    
    async def stream_run(self, user_input: str) -> AsyncGenerator[Dict, None]:
        """流式执行
        
        **改造：支持用户等待和响应注入**
        """
        # 1. 记录用户输入
        self.session.emit_event(EventType.USER_INPUT, {"content": user_input})
        
        # 2. 创建取消信号
        signal = AbortSignal()
        
        # 3. 执行对话
        result = await self.harness.run_conversation(signal)
        
        # 4. **检查等待状态**
        if isinstance(result, dict) and result.get("status") == "waiting_for_user":
            # 流式返回等待信息
            yield {
                "type": "awaiting_user_input",
                "request": result["request"],
            }
            
            # **阻塞等待用户响应**（由 inject_user_input 唤醒）
            await self._user_input_event.wait()
            
            # 获取注入的响应
            user_response = self._pending_user_response
            
            # 清理状态
            self._user_input_event.clear()
            self._pending_user_response = None
            
            # 恢复执行
            final_result = await self.harness.resume_with_user_response(
                user_response, signal
            )
            
            yield {"type": "final", "content": final_result}
        else:
            # 正常完成
            yield {"type": "final", "content": result}
    
    def inject_user_input(self, response: AskUserResult) -> None:
        """注入用户响应（外部调用）
        
        Args:
            response: 用户响应数据
        
        用法：
            # 在 main.py 或外部系统调用
            agent.inject_user_input(AskUserResult(
                request_id="abc123",
                responses=[UserResponse(question_id="0", selected=["Yes"])],
            ))
        """
        self._pending_user_response = response
        self._user_input_event.set()
    
    def cancel_current_execution(self) -> None:
        """取消当前执行"""
        self._abort_signal.abort()
        self._user_input_event.set()  # 唤醒等待
```

### 2.6 Session 层改造

```python
# src/session_event_stream.py - 扩展

class SessionEventStream:
    """不可变事件流"""
    
    def emit_user_question(self, request: AskUserRequest) -> None:
        """记录用户问题事件"""
        self.emit_event(EventType.USER_QUESTION, {
            "request_id": request.request_id,
            "questions": [
                {
                    "question": q.question,
                    "header": q.header,
                    "options": [{"label": o.label, "value": o.value} for o in q.options],
                    "multi_select": q.multi_select,
                }
                for q in request.questions
            ],
            "created_at": request.created_at,
        })
    
    def emit_user_response(self, response: AskUserResult) -> None:
        """记录用户响应事件"""
        self.emit_event(EventType.USER_RESPONSE, {
            "request_id": response.request_id,
            "responses": [
                {
                    "question_id": r.question_id,
                    "selected": r.selected,
                    "custom_input": r.custom_input,
                }
                for r in response.responses
            ],
            "cancelled": response.cancelled,
            "timeout": response.timeout,
        })
    
    def get_pending_question(self) -> Optional[AskUserRequest]:
        """获取当前等待的问题"""
        # 从最近的 USER_QUESTION 事件中查找
        # 如果后面没有 USER_RESPONSE，则为 pending
        for event in reversed(self._events):
            if event.type == EventType.USER_RESPONSE:
                return None  # 已响应
            if event.type == EventType.USER_QUESTION:
                return AskUserRequest(**event.data)
        return None
```

### 2.7 main.py 改造

```python
# main.py - 改造

async def interactive_loop(agent: AgentLoop):
    """交互式主循环
    
    **改造：处理用户等待状态**
    """
    print("Seed Agent started. Type your message (or Ctrl+C to exit).")
    
    while True:
        try:
            # 获取用户输入
            user_input = await async_input("You: ")
            
            if user_input.lower() in ('exit', 'quit'):
                break
            
            # 流式执行
            async for chunk in agent.stream_run(user_input):
                if chunk["type"] == "chunk":
                    print(chunk["content"], end="", flush=True)
                
                elif chunk["type"] == "awaiting_user_input":
                    # **处理用户等待**
                    request = chunk["request"]
                    
                    # 显示问题
                    print("\n[Agent asks:]")
                    for i, q in enumerate(request.questions):
                        print(f"  {i+1}. {q.question}")
                        for j, opt in enumerate(q.options):
                            print(f"     [{j+1}] {opt.label}")
                    
                    # 获取用户响应
                    if len(request.questions) == 1 and len(request.questions[0].options) == 2:
                        # 简单确认 - 快速处理
                        answer = await async_input("Your choice (1/2 or custom): ")
                    else:
                        # 多问题 - 详细处理
                        answer = await async_input("Your answer: ")
                    
                    # 解析响应
                    response = parse_user_answer(request, answer)
                    
                    # 注入响应
                    agent.inject_user_input(response)
                
                elif chunk["type"] == "final":
                    print(f"\n{chunk['content']}")
        
        except KeyboardInterrupt:
            # 取消当前执行
            agent.cancel_current_execution()
            print("\n[Execution cancelled]")
            continue

def parse_user_answer(request: AskUserRequest, answer: str) -> AskUserResult:
    """解析用户输入为结构化响应"""
    responses = []
    
    # 简单情况：单个问题
    if len(request.questions) == 1:
        q = request.questions[0]
        
        # 尝试匹配选项编号
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(q.options):
                responses.append(UserResponse(
                    question_id="0",
                    selected=[q.options[idx].value or q.options[idx].label],
                ))
            else:
                # 自定义输入
                responses.append(UserResponse(
                    question_id="0",
                    selected=[answer],
                    custom_input=answer,
                ))
        except ValueError:
            # 自定义输入
            responses.append(UserResponse(
                question_id="0",
                selected=[answer],
                custom_input=answer,
            ))
    
    return AskUserResult(
        request_id=request.request_id,
        responses=responses,
        cancelled=False,
    )
```

---

## 第三部分：任务打断机制设计

### 3.1 设计理念

**AbortController Pattern**（参考 qwen-code）：
- 每个任务关联一个 AbortController
- 取消时调用 `abort()` 发送信号
- 各执行点检查 `signal.aborted` 状态
- 优雅期让自然完成优先

### 3.2 AbortSignal 实现

```python
# src/abort_signal.py (新文件)

import asyncio
from typing import Callable, List
from dataclasses import dataclass, field

@dataclass
class AbortSignal:
    """取消信号（类似 JavaScript AbortSignal）"""
    
    aborted: bool = False
    reason: str = ""
    _listeners: List[Callable] = field(default_factory=list)
    
    def abort(self, reason: str = "") -> None:
        """触发取消"""
        self.aborted = True
        self.reason = reason
        for listener in self._listeners:
            listener(self)
        self._listeners.clear()
    
    def add_listener(self, listener: Callable) -> None:
        """添加取消监听器"""
        self._listeners.append(listener)
    
    def remove_listener(self, listener: Callable) -> None:
        """移除监听器"""
        self._listeners.remove(listener)

class AbortController:
    """取消控制器"""
    
    def __init__(self):
        self.signal = AbortSignal()
    
    def abort(self, reason: str = "") -> None:
        """取消关联的任务"""
        self.signal.abort(reason)
```

### 3.3 BackgroundTaskRegistry

```python
# src/background_task_registry.py (新文件)

import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .abort_signal import AbortController

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class BackgroundTaskEntry:
    """后台任务条目"""
    task_id: str
    prompt: str
    status: TaskStatus
    abort_controller: AbortController
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None

CANCEL_GRACE_SECONDS = 5  # 优雅等待期

class BackgroundTaskRegistry:
    """后台任务注册表
    
    参考 qwen-code 的 background-tasks.ts 实现
    """
    
    def __init__(self):
        self._tasks: Dict[str, BackgroundTaskEntry] = {}
        self._lock = asyncio.Lock()
    
    def register(self, task_id: str, prompt: str) -> BackgroundTaskEntry:
        """注册新任务"""
        entry = BackgroundTaskEntry(
            task_id=task_id,
            prompt=prompt,
            status=TaskStatus.PENDING,
            abort_controller=AbortController(),
        )
        self._tasks[task_id] = entry
        return entry
    
    def start(self, task_id: str) -> None:
        """标记任务开始"""
        entry = self._tasks.get(task_id)
        if entry:
            entry.status = TaskStatus.RUNNING
            entry.started_at = datetime.now()
    
    def complete(self, task_id: str, result: str) -> None:
        """标记任务完成"""
        entry = self._tasks.get(task_id)
        if entry:
            entry.status = TaskStatus.COMPLETED
            entry.completed_at = datetime.now()
            entry.result = result
    
    def fail(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        entry = self._tasks.get(task_id)
        if entry:
            entry.status = TaskStatus.FAILED
            entry.completed_at = datetime.now()
            entry.error = error
    
    def cancel(self, task_id: str) -> bool:
        """取消任务
        
        Returns:
            是否成功触发取消（任务可能在优雅期自然完成）
        """
        entry = self._tasks.get(task_id)
        if not entry or entry.status != TaskStatus.RUNNING:
            return False
        
        # 触发 abort 信号
        entry.abort_controller.abort(reason="user_cancelled")
        
        # 设置优雅等待期
        # 自然完成处理器通常会赢得竞争
        asyncio.create_task(self._grace_period_handler(task_id))
        
        return True
    
    async def _grace_period_handler(self, task_id: str) -> None:
        """优雅等待期处理"""
        await asyncio.sleep(CANCEL_GRACE_SECONDS)
        
        entry = self._tasks.get(task_id)
        if entry and entry.status == TaskStatus.RUNNING:
            # 超过优雅期，强制取消
            entry.status = TaskStatus.CANCELLED
            entry.completed_at = datetime.now()
            entry.error = "Cancelled after grace period"
    
    def cancel_all(self) -> None:
        """取消所有运行中的任务"""
        for task_id, entry in self._tasks.items():
            if entry.status == TaskStatus.RUNNING:
                self.cancel(task_id)
    
    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        entry = self._tasks.get(task_id)
        return entry.status if entry else None
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Dict]:
        """列出任务"""
        result = []
        for entry in self._tasks.values():
            if status is None or entry.status == status:
                result.append({
                    "task_id": entry.task_id,
                    "prompt": entry.prompt[:50] + "...",
                    "status": entry.status.value,
                    "created_at": entry.created_at.isoformat(),
                })
        return result
    
    def cleanup(self, task_id: Optional[str] = None) -> None:
        """清理任务资源"""
        if task_id:
            self._tasks.pop(task_id, None)
        else:
            # 清理所有已完成的任务
            to_remove = [
                tid for tid, entry in self._tasks.items()
                if entry.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ]
            for tid in to_remove:
                self._tasks.pop(tid)
```

### 3.4 TaskStop 工具

```python
# src/tools/task_stop.py (新文件)

from typing import Optional
from ..background_task_registry import BackgroundTaskRegistry, TaskStatus

def task_stop(task_id: str) -> str:
    """停止后台任务
    
    Args:
        task_id: 要停止的任务ID
    
    Returns:
        操作结果信息
    """
    # 获取全局注册表（由 AgentLoop 初始化）
    registry = get_background_task_registry()
    if not registry:
        return "Error: Task registry not initialized"
    
    status = registry.get_status(task_id)
    if not status:
        return f"Error: Task '{task_id}' not found"
    
    if status != TaskStatus.RUNNING:
        return f"Task '{task_id}' is not running (status: {status.value})"
    
    # 触发取消
    success = registry.cancel(task_id)
    
    if success:
        return f"Task '{task_id}' cancellation initiated. Will complete within {CANCEL_GRACE_SECONDS}s grace period."
    else:
        return f"Failed to cancel task '{task_id}'"

def get_background_task_registry() -> Optional[BackgroundTaskRegistry]:
    """获取全局任务注册表"""
    global _global_registry
    return _global_registry

def init_background_task_registry(registry: BackgroundTaskRegistry) -> None:
    """初始化全局注册表"""
    global _global_registry
    _global_registry = registry
```

### 3.5 Harness 层取消支持

```python
# src/harness.py - 改造

class Harness:
    """控制器：驱动循环，路由工具"""
    
    async def run_cycle(self, signal: AbortSignal) -> Dict:
        """执行一轮循环
        
        Args:
            signal: 取消信号（新增参数）
        """
        # **检查取消信号**
        if signal.aborted:
            return {"status": "cancelled", "reason": signal.reason}
        
        # ... 正常执行 ...
        
        # 在关键点检查取消
        if signal.aborted:
            return {"status": "cancelled", "reason": signal.reason}
        
        return {"status": "continue", ...}
    
    async def run_conversation(self, signal: AbortSignal) -> str:
        """运行完整对话
        
        Args:
            signal: 取消信号
        """
        iteration = 0
        while iteration < self.max_iterations:
            # 每轮开始检查取消
            if signal.aborted:
                return f"[CANCELLED: {signal.reason}]"
            
            iteration += 1
            result = await self.run_cycle(signal)
            
            if result["status"] == "cancelled":
                return f"[CANCELLED: {result['reason']}]"
            
            # ... 处理其他状态 ...
        
        return "[MAX_ITERATIONS]"
```

### 3.6 AgentLoop 层取消支持

```python
# src/agent_loop.py - 改造

class AgentLoop:
    """主执行引擎"""
    
    def __init__(self, ...):
        # ... 现有初始化 ...
        
        # 取消控制
        self._abort_controller: AbortController = AbortController()
        self._background_task_registry: BackgroundTaskRegistry = BackgroundTaskRegistry()
        
        # 初始化全局注册表
        init_background_task_registry(self._background_task_registry)
    
    async def stream_run(self, user_input: str) -> AsyncGenerator[Dict, None]:
        """流式执行"""
        # 重置取消信号
        self._abort_controller = AbortController()
        signal = self._abort_controller.signal
        
        # 执行
        result = await self.harness.run_conversation(signal)
        
        # ... 处理结果 ...
    
    def cancel_current_execution(self) -> None:
        """取消当前执行"""
        self._abort_controller.abort(reason="user_interrupt")
        
        # 同时取消所有后台任务
        self._background_task_registry.cancel_all()
        
        # 唤醒用户等待（如果有）
        self._user_input_event.set()
```

### 3.7 信号处理（SIGINT/SIGTERM）

```python
# main.py - 改造

import signal
import asyncio

_shutdown_in_progress = False

async def graceful_shutdown(agent: AgentLoop, reason: str = "signal") -> None:
    """优雅关闭
    
    参考 qwen-code 的 acpAgent.ts 实现
    """
    global _shutdown_in_progress
    if _shutdown_in_progress:
        return
    _shutdown_in_progress = True
    
    print(f"\n[Shutting down: {reason}]")
    
    # 1. 触发 SESSION_END 钩子
    await agent.hooks.trigger(HookPoint.SESSION_END, {
        "reason": reason,
    })
    
    # 2. 取消所有运行中的任务
    agent.cancel_current_execution()
    
    # 3. 保存会话状态
    agent.session.persist()
    
    # 4. 清理后台任务
    agent._background_task_registry.cancel_all()
    
    # 5. 清理超时保护（5秒）
    try:
        await asyncio.wait_for(
            cleanup_resources(agent),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        print("[Cleanup timeout - forcing exit]")
    
    print("[Agent powered down. Goodbye!]")

async def cleanup_resources(agent: AgentLoop) -> None:
    """清理资源"""
    # 清理 sandbox
    if agent.sandbox:
        agent.sandbox.cleanup()
    
    # 清理后台任务
    agent._background_task_registry.cleanup()

def setup_signal_handlers(agent: AgentLoop, loop: asyncio.AbstractEventLoop) -> None:
    """设置信号处理器"""
    
    def handle_sigterm():
        asyncio.create_task(graceful_shutdown(agent, "SIGTERM"))
    
    def handle_sigint():
        asyncio.create_task(graceful_shutdown(agent, "SIGINT"))
    
    # Windows 兼容处理
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, lambda s, f: handle_sigterm())
    if hasattr(signal, 'SIGINT'):
        signal.signal(signal.SIGINT, lambda s, f: handle_sigint())
    
    # Windows 特殊处理
    if os.name == 'nt':
        # Windows 使用不同机制
        try:
            loop.add_signal_handler(signal.SIGINT, handle_sigint)
        except NotImplementedError:
            pass

async def interactive_loop(agent: AgentLoop):
    """交互式主循环
    
    改造：Ctrl+C 双击退出
    """
    loop = asyncio.get_event_loop()
    setup_signal_handlers(agent, loop)
    
    ctrl_c_count = 0
    last_ctrl_c_time = 0
    
    while True:
        try:
            user_input = await async_input("You: ")
            ctrl_c_count = 0  # 重置计数
            
            if user_input.lower() in ('exit', 'quit'):
                await graceful_shutdown(agent, "user_exit")
                break
            
            # 执行...
            async for chunk in agent.stream_run(user_input):
                # ... 处理 chunk ...
        
        except KeyboardInterrupt:
            # Ctrl+C 处理
            now = time.time()
            if now - last_ctrl_c_time < 2.0:  # 2秒内第二次
                await graceful_shutdown(agent, "ctrl_c_double")
                break
            else:
                # 第一次 Ctrl+C - 取消当前执行
                ctrl_c_count = 1
                last_ctrl_c_time = now
                agent.cancel_current_execution()
                print("\n[Execution cancelled. Press Ctrl+C again within 2s to exit.]")
                continue
```

### 3.8 Lifecycle Hooks 扩展

```python
# src/lifecycle_hooks.py - 扩展 HookPoint

class HookPoint(str, Enum):
    # ... 现有钩子点 ...
    
    # 新增：取消相关钩子
    EXECUTION_CANCEL = "execution_cancel"      # 执行被取消
    TASK_CANCEL = "task_cancel"                # 后台任务取消
    GRACE_PERIOD_START = "grace_period_start"  # 优雅期开始
    GRACE_PERIOD_END = "grace_period_end"      # 优雅期结束
    
    # 新增：关闭相关钩子
    SHUTDOWN_START = "shutdown_start"          # 关闭开始
    SHUTDOWN_COMPLETE = "shutdown_complete"    # 关闭完成
```

---

## 第四部分：集成设计

### 4.1 执行流程图

```
完整执行流程（含用户等待和取消）：

┌─────────────────────────────────────────────────────────────┐
│  main.py: interactive_loop()                                │
│  - 获取用户输入                                               │
│  - 调用 agent.stream_run()                                   │
│  - 处理 awaiting_user_input chunk                            │
│  - 收集用户响应 → agent.inject_user_input()                  │
│  - Ctrl+C → agent.cancel_current_execution()                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  AgentLoop: stream_run(user_input)                          │
│  - 创建 AbortController/AbortSignal                          │
│  - 调用 harness.run_conversation(signal)                     │
│  - 检查等待状态 → 返回 awaiting_user_input                    │
│  - 等待 _user_input_event                                    │
│  - 恢复 → harness.resume_with_user_response()                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Harness: run_conversation(signal)                          │
│  - 循环：run_cycle()                                          │
│  - 每轮检查 signal.aborted                                    │
│  - 检测 ask_user 等待 → 返回 waiting_for_user                 │
│  - resume_with_user_response() → 继续循环                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Harness: run_cycle(signal)                                 │
│  - 构建上下文 → Session.build_context_for_llm()               │
│  - LLM 调用 → LLMClient.chat_completion()                    │
│  - 执行工具 → _execute_tool_calls()                           │
│  - 检查 get_pending_ask_user_request()                       │
│  - 触发钩子 → hooks.trigger(TOOL_CALL_AFTER)                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Tools: ask_user(question, options)                         │
│  - 构造 Question 结构                                         │
│  - 设置 _pending_ask_user_request                            │
│  - 返回 [AWAITING_USER_INPUT] 标记                            │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 取消流程图

```
取消执行流程：

┌─────────────────────────────────────────────────────────────┐
│  触发源                                                       │
│  - Ctrl+C (SIGINT)                                           │
│  - SIGTERM                                                    │
│  - task_stop 工具调用                                          │
│  - 外部 SDK 调用                                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  AbortController.abort(reason)                              │
│  - 设置 signal.aborted = True                                │
│  - 触发所有监听器                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Harness: run_cycle() 检测                                   │
│  - if signal.aborted: return {"status": "cancelled"}         │
│  - 返回取消状态给上层                                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  BackgroundTaskRegistry.cancel(task_id)                     │
│  - abort_controller.abort()                                  │
│  - status = TaskStatus.CANCELLED                             │
│  - 启动 5秒优雅等待期                                          │
│  - 自然完成处理器可能赢得竞争                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Graceful Shutdown                                           │
│  - 触发 SESSION_END 钩子                                      │
│  - 取消所有后台任务                                            │
│  - 保存会话状态                                                │
│  - 清理资源（5秒超时保护）                                      │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 文件结构

```
新增/修改文件清单：

新增文件：
├── src/abort_signal.py                    # AbortSignal/AbortController 实现
├── src/background_task_registry.py        # 后台任务注册表
├── src/tools/ask_user_types.py            # Ask User 数据类型定义
├── src/tools/task_stop.py                 # TaskStop 工具实现

修改文件：
├── src/agent_loop.py                      # AgentLoop 改造（等待/取消支持）
├── src/harness.py                         # Harness 改造（等待状态/取消检测）
├── src/tools/builtin_tools.py             # ask_user 工具改造
├── src/session_event_stream.py            # EventType 扩展
├── src/lifecycle_hooks.py                 # HookPoint 扩展
├── main.py                                # 交互循环改造（信号处理/Ctrl+C）
```

---

## 第五部分：API 设计

### 5.1 ask_user 工具 API

```python
# 工具调用参数
{
    "name": "ask_user",
    "arguments": {
        "question": "Should I proceed with file deletion?",
        "options": ["Yes, delete", "No, keep", "Show details first"],
        "header": "Confirm delete",
        "multi_select": False
    }
}

# 返回格式（等待状态）
"[AWAITING_USER_INPUT] request_id=abc123
Should I proceed with file deletion?
Options: Yes, delete, No, keep, Show details first"

# 用户响应注入后，工具结果
"User selected: ['Yes, delete']"
```

### 5.2 task_stop 工具 API

```python
# 工具调用参数
{
    "name": "task_stop",
    "arguments": {
        "task_id": "bg_12345"
    }
}

# 返回格式
"Task 'bg_12345' cancellation initiated. Will complete within 5s grace period."
```

### 5.3 SDK 外部接口

```python
# 程序化使用示例
from seed_agent import AgentLoop, AbortController, AskUserResult, UserResponse

# 创建 agent
agent = AgentLoop(gateway=gateway, system_prompt="...")

# 执行（带取消控制）
controller = AbortController()

async def run_task():
    async for chunk in agent.stream_run("Long task"):
        if chunk["type"] == "awaiting_user_input":
            # 外部系统收集用户响应
            response = collect_user_response_external(chunk["request"])
            agent.inject_user_input(response)
        elif chunk["type"] == "final":
            return chunk["content"]

# 取消执行
controller.abort(reason="external_cancel")
agent.cancel_current_execution()

# 注入用户响应
agent.inject_user_input(AskUserResult(
    request_id="abc123",
    responses=[UserResponse(question_id="0", selected=["Yes"])],
))
```

---

## 第六部分：测试设计

### 6.1 Ask User 测试场景

| 场景 | 测试内容 | 预期结果 |
|------|----------|----------|
| 简单确认 | ask_user("Continue?", ["Yes", "No"]) | 显示问题，等待用户选择 |
| 多选项 | ask_user("Choice?", ["A", "B", "C", "D"]) | 显示4个选项 |
| 多选 | ask_user("Select files", options, multi_select=True) | 允许选择多个 |
| 用户取消 | 用户输入 "cancel" | 返回 USER_CANCELLED |
| 自定义输入 | 用户输入非选项内容 | 记录为 custom_input |
| 超时 | 用户长时间不响应 | 触发 timeout（可选） |

### 6.2 取消测试场景

| 场景 | 测试内容 | 预期结果 |
|------|----------|----------|
| Ctrl+C 单次 | 执行中按 Ctrl+C | 取消当前执行，显示提示 |
| Ctrl+C 双次 | 2秒内再按 Ctrl+C | 优雅关闭并退出 |
| SIGTERM | 发送 SIGTERM 信号 | 触发 graceful_shutdown |
| task_stop 工具 | 调用 task_stop(task_id) | 取消指定后台任务 |
| 优雅期竞争 | 取消时任务刚好完成 | 自然完成处理器获胜 |
| 多任务取消 | cancel_all() | 所有任务并行取消 |

### 6.3 集成测试场景

| 场景 | 测试内容 | 预期结果 |
|------|----------|----------|
| Ask + Cancel | ask_user 等待时取消 | 唤醒等待，返回取消 |
| Resume after cancel | 取消后继续对话 | 清理状态，正常继续 |
| Hook 触发 | 取消时检查钩子 | SESSION_PAUSE/RESUME 正确触发 |
| 状态持久化 | 等待时崩溃恢复 | Session 恢复等待状态 |

---

## 第七部分：实施路径

### 7.1 实施阶段

**Phase 1：基础数据结构**（预计 1 天）
- 创建 `abort_signal.py`
- 创建 `ask_user_types.py`
- 扩展 `EventType` 枚举

**Phase 2：Ask User 机制**（预计 2 天）
- 改造 `builtin_tools.py` 的 `ask_user`
- 改造 `harness.py` 的等待状态检测
- 改造 `agent_loop.py` 的响应注入
- 改造 `main.py` 的用户交互处理

**Phase 3：取消机制**（预计 2 天）
- 创建 `background_task_registry.py`
- 创建 `task_stop.py` 工具
- 改造 `harness.py` 的取消检测
- 改造 `agent_loop.py` 的取消控制
- 实现信号处理

**Phase 4：钩子和清理**（预计 1 天）
- 扩展 `HookPoint` 枚举
- 实现优雅关闭逻辑
- 实现清理超时保护

**Phase 5：测试和文档**（预计 1 天）
- 编写单元测试
- 编写集成测试
- 更新 API 文档

### 7.2 优先级排序

| 优先级 | 功能 | 原因 |
|--------|------|------|
| P0 | ask_user 等待机制 | 核心交互需求 |
| P0 | Ctrl+C 取消 | 基础可用性需求 |
| P1 | task_stop 工具 | 后台任务管理 |
| P1 | 优雅关闭 | 稳定性保障 |
| P2 | 多问题支持 | 高级功能 |
| P2 | SDK 外部接口 | 集成便利性 |

---

## 附录 A：与 qwen-code 的差异对比

| 特性 | qwen-code | seed-agent 设计 | 原因 |
|------|-----------|-----------------|------|
| 语言 | TypeScript | Python | 语言差异 |
| 异步模型 | Promise/async | asyncio.Event | Python 模式 |
| 状态机 | explicit status enum | dict + status 字段 | 简化实现 |
| 确认回调 | onConfirm(outcome) | inject_user_input() | 控制流差异 |
| UI 组件 | React Dialog | CLI + external | 无 WebUI |
| 权限系统 | PermissionManager | 简化版（可选） | 复杂度控制 |
| ACP 模式 | STREAM_JSON input | 未实现 | 暂无需求 |

---

## 附录 B：参考文件清单

| qwen-code 文件 | 机制 | 对应 seed-agent |
|-----------------|------|-----------------|
| `askUserQuestion.ts` | Ask User 工具 | `builtin_tools.py` |
| `coreToolScheduler.ts` | 等待状态机 | `harness.py` |
| `background-tasks.ts` | 后台任务注册表 | `background_task_registry.py` |
| `task-stop.ts` | TaskStop 工具 | `task_stop.py` |
| `acpAgent.ts` | 信号处理 | `main.py` |
| `Session.ts` | 取消控制 | `agent_loop.py` |

---

## 文档版本

- **版本**: 1.0
- **日期**: 2026-05-03
- **作者**: Seed Agent Team
- **状态**: 设计完成，待实施