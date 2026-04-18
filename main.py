import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path to allow imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent_loop import AgentLoop
from client import LLMGateway

async def main():
    """交互式主循环入口"""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.json')
    
    print("Initializing Agent...")
    try:
        # 初始化网关和 Agent
        gateway = LLMGateway(config_path)
        agent = AgentLoop(gateway=gateway)
        print("Agent initialized successfully. Type 'exit' to quit.\n")
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        return

    print("Starting interactive loop...")
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit']:
                break
            if not user_input.strip():
                continue
            
            print("Agent: ", end="", flush=True)
            
            # 使用流式输出提升交互体验
            async for chunk in agent.stream_run(user_input):
                if chunk['type'] == 'chunk':
                    print(chunk['content'], end="", flush=True)
                elif chunk['type'] == 'final':
                    print() # 响应结束换行
            
            print("-" * 50) # 分隔符
            
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            break
        except Exception as e:
            print(f"\nError occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())