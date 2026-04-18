import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent_loop import AgentLoop
from src.client import LLMGateway

async def main():
    print("--- Seed Agent Example ---")
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
    try:
        gateway = LLMGateway(config_path)
        agent = AgentLoop(gateway=gateway, max_iterations=2)
        
        def get_current_time():
            """Get the current time."""
            import datetime
            return datetime.datetime.now().isoformat()
            
        agent.tools.register("get_time", get_current_time, {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Get the current time",
                "parameters": {"type": "object", "properties": {}}
            }
        })
        
        print(f"Registered tools: {agent.tools.get_schemas()}")
        
        print("Running agent loop...")
        async for chunk in agent.stream_run("What time is it?"):
            if chunk['type'] == 'chunk':
                print(chunk['content'], end='', flush=True)
            elif chunk['type'] == 'final':
                print(f"\n[Final: {chunk['content']}]")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
