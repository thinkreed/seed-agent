import argparse
import asyncio
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path to allow imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Setup cross-platform logging to .seed/logs
LOG_DIR = Path(__file__).parent / ".seed" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "seed_agent.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("seed_agent")

from agent_loop import AgentLoop
from client import LLMGateway

async def main(args=None):
    """交互式主循环入口"""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.json')
    
    # Load system prompt
    prompt_path = os.path.join(os.path.dirname(__file__), 'core_principles', 'system_prompts_en.md')
    system_prompt = None
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()

    print("Initializing Agent...")
    try:
        # 初始化网关和 Agent
        gateway = LLMGateway(config_path)
        agent = AgentLoop(gateway=gateway, system_prompt=system_prompt)
        print("Agent initialized successfully. Type 'exit' to quit.\n")
    except Exception as e:
        logger.exception("Failed to initialize agent")
        return

    # One-shot chat mode
    if args and args.chat:
        try:
            response = await agent.run(args.chat)
            print(response)
        except Exception as e:
            logger.exception("One-shot chat failed")
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
            logger.exception("Error occurred during interaction")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Agent CLI")
    parser.add_argument('--chat', '-c', type=str, help="One-shot chat message")
    args = parser.parse_args()
    asyncio.run(main(args))