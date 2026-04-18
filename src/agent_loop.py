import asyncio
import json
from typing import List, Dict, Optional, AsyncGenerator
from tools import ToolRegistry
from tools.builtin_tools import run_code, read_file, write_file, list_files
from client import LLMGateway

def estimate_content_length(content: str) -> int:
    """简单估算内容长度 (字符数 * 1.5 粗略模拟 token 消耗，中英文混排)"""
    if not content:
        return 0
    # 粗略估算：中文约等于1 token，英文单词约等于1-1.3 token。这里直接用 len 做简单截断基准
    return len(content)

class MaxIterationsExceeded(Exception):
    """超过最大迭代次数异常"""
    pass

class ProviderNotFoundError(Exception):
    """提供商不存在异常"""
    pass

class ToolNotFoundError(Exception):
    """工具不存在异常"""
    pass

class AgentLoop:
    """Agent 主循环"""
    
    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str = None,
        system_prompt: str = None,
        max_iterations: int = 10
    ):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        
        self.history: List[Dict] = []
        self.tools = ToolRegistry()
        from tools.builtin_tools import register_builtin_tools
        register_builtin_tools(self.tools)
        self._pending_user_input: Optional[str] = None  # 待处理的用户输入
    
    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents['defaults'].defaults.primary
    
    def _build_messages(self) -> List[Dict]:
        """构建完整的消息列表，包含上下文自动截断"""
        self._trim_history()
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        return messages

    def _trim_history(self):
        """根据模型上下文窗口限制，裁剪历史消息"""
        if not self.history:
            return

        try:
            model_config = self.gateway.get_model_config(self.model_id)
            max_context = model_config.contextWindow
        except Exception:
            max_context = 8000

        # 限制在 contextWindow 的 80% 以内，预留响应空间
        limit = int(max_context * 0.8)
        system_len = estimate_content_length(self.system_prompt) if self.system_prompt else 0
        available = max(500, limit - system_len)

        # 估算历史总长度
        total_len = sum(estimate_content_length(msg.get('content', '')) for msg in self.history)
        
        if total_len > available:
            # 逆序保留最近的消息
            messages_to_keep = []
            current_len = 0
            for msg in reversed(self.history):
                length = estimate_content_length(msg.get('content', ''))
                if current_len + length > available:
                    # 如果还没保留任何消息，强制保留最后一条（通常是用户最新的输入）
                    if not messages_to_keep:
                        messages_to_keep.append(msg)
                    break
                current_len += length
                messages_to_keep.append(msg)
            
            self.history = list(reversed(messages_to_keep))
            print(f"[Context Trimmed]: History reduced to {len(self.history)} messages.")
    
    async def run(self, user_input: str) -> str:
        """处理用户输入,返回最终响应
        
        用户消息优先原则:
        - 在处理过程中收到新的用户输入,立即中断当前处理
        - 优先响应新的用户消息
        
        Args:
            user_input: 用户输入文本
        Returns:
            Agent 的最终响应文本
        """
        # 1. 添加用户输入到历史
        self.history.append({"role": "user", "content": user_input})
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            # 检查是否有新的用户输入(中断机制)
            if self._pending_user_input:
                new_input = self._pending_user_input
                self._pending_user_input = None
                self.history.append({"role": "user", "content": new_input})
                iteration = 0  # 重置迭代计数
            
            # 2. 调用 LLM
            messages = self._build_messages()
            response = await self.gateway.chat_completion(
                self.model_id,
                messages,
                tools=self.tools.get_schemas()
            )
            
            # 3. 解析响应
            choice = response['choices'][0]
            message = choice['message']
            
            # 添加到历史
            self.history.append(message)
            
            # 4. 检查是否有工具调用
            if message.get('tool_calls'):
                tool_results = await self._execute_tool_calls(message['tool_calls'])
                self.history.extend(tool_results)
                # 继续循环,让 LLM 处理工具结果
            else:
                # 5. 无工具调用,返回最终响应
                return message.get('content', '')
        
        raise MaxIterationsExceeded(
            f"Agent exceeded maximum iterations ({self.max_iterations})"
        )
    
    async def stream_run(self, user_input: str) -> AsyncGenerator[Dict, None]:
        """流式处理用户输入
        
        Yields:
            {"type": "chunk", "content": "..."}  # 文本块
            {"type": "final", "content": "..."}  # 最终响应
            {"type": "tool_call", "name": "...", "args": {...}}  # 工具调用
        """
        self.history.append({"role": "user", "content": user_input})
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            messages = self._build_messages()
            full_content = ""
            tool_calls = []
            
            # 流式获取响应
            async for chunk in self.gateway.stream_chat_completion(
                self.model_id,
                messages,
                tools=self.tools.get_schemas()
            ):
                # 提取内容
                delta = chunk['choices'][0].get('delta', {})
                content = delta.get('content')
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}
                
                # 提取工具调用
                tc = delta.get('tool_calls')
                if tc:
                    tool_calls.extend(tc)
            
            # 构建助手消息
            assistant_message = {
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": tool_calls if tool_calls else None
            }
            self.history.append(assistant_message)
            
            # 处理工具调用
            if tool_calls:
                yield {"type": "tool_call", "calls": tool_calls}
                tool_results = await self._execute_tool_calls(tool_calls)
                self.history.extend(tool_results)
            else:
                yield {"type": "final", "content": full_content}
                return
    
    async def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """批量并行执行工具调用
        
        Args:
            tool_calls: LLM 返回的工具调用列表
        Returns:
            工具结果消息列表 (role: "tool")
        """
        async def _run_single_call(tool_call: Dict) -> Dict:
            tool_id = tool_call['id']
            tool_name = tool_call['function']['name']
            # Handle potential dict or string for arguments
            raw_args = tool_call['function']['arguments']
            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            
            try:
                result = await self.tools.execute(tool_name, **tool_args)
                return {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": str(result)
                }
            except Exception as e:
                return {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": f"Error: {str(e)}"
                }
        
        # Execute all tool calls concurrently
        return await asyncio.gather(*[_run_single_call(tc) for tc in tool_calls])
    
    def clear_history(self):
        """清空对话历史"""
        self.history.clear()
    
    def interrupt(self, user_input: str):
        """中断当前处理,优先响应用户输入
        
        当 agent 正在处理(如执行工具调用)时,
        用户可以通过此方法发送新的指令并优先处理。
        
        Args:
            user_input: 新的用户输入
        """
        self._pending_user_input = user_input