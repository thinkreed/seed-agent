import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent_loop import AgentLoop
from client import LLMGateway

async def main():
    config_path = os.path.join(os.path.expanduser("~"), ".seed", "config.json")
    gateway = LLMGateway(config_path)
    agent = AgentLoop(gateway=gateway)
    
    print("Testing stream_run...")
    async for chunk in agent.stream_run("Tell me a short joke"):
        if chunk.get('type') == 'chunk':
            print(chunk['content'], end='', flush=True)
        elif chunk.get('type') == 'final':
            print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())