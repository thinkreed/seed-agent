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

# Setup cross-platform logging to ~/.seed/logs with daily rotation
LOG_DIR = Path(os.path.expanduser("~")) / ".seed" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

from datetime import date

# 按天分割日志文件：seed_agent_2026-04-18.log
log_file = LOG_DIR / f"seed_agent_{date.today().isoformat()}.log"
file_handler = logging.FileHandler(log_file, encoding="utf-8")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        file_handler
    ]
)
logger = logging.getLogger("seed_agent")

from agent_loop import AgentLoop
from client import LLMGateway
from autonomous import AutonomousExplorer


def on_autonomous_complete(response: str):
    """自主探索完成回调"""
    print("\n[自主探索完成] " + "-" * 40)
    print(response[:500] if len(response) > 500 else response)
    print("-" * 50 + "\nYou: ", end="", flush=True)


async def main(args=None):
    """交互式主循环入口"""
    config_path = os.path.join(os.path.expanduser("~"), ".seed", "config.json")

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

        # One-shot chat mode：不启动自主探索
        if args and args.chat:
            try:
                response = await agent.run(args.chat)
                print(response)
            except Exception as e:
                logger.exception("One-shot chat failed")
            return

        # 交互模式：启动自主探索监控和定时任务调度
        explorer = AutonomousExplorer(agent, on_explore_complete=on_autonomous_complete)
        await explorer.start()
        await agent.scheduler.start()

        print("Agent initialized successfully. Type 'exit' to quit.\n")
        print("Starting interactive loop (自主探索: 15分钟空闲触发, 定时任务: 自动执行)...")
    except Exception as e:
        logger.exception("Failed to initialize agent")
        return

    while True:
        try:
            # 使用 asyncio.to_thread 避免 input() 阻塞事件循环
            # 这样自主探索的空闲监控任务才能正常运行
            user_input = await asyncio.to_thread(input, "You: ")
            if user_input.lower() in ['exit', 'quit']:
                await explorer.stop()
                await agent.scheduler.stop()
                break
            if not user_input.strip():
                continue

            # 记录用户活动
            explorer.record_activity()

            print("Agent: ⏳", end="", flush=True)
            is_first_chunk = True

            # 使用流式输出提升交互体验
            async for chunk in agent.stream_run(user_input):
                if is_first_chunk:
                    # 清除 loading 提示
                    sys.stdout.write('\b \b')
                    is_first_chunk = False

                if chunk['type'] == 'chunk':
                    print(chunk['content'], end="", flush=True)
                elif chunk['type'] == 'final':
                    print() # 响应结束换行

            print("-" * 50) # 分隔符

        except EOFError:
            # stdin 关闭（如管道输入结束），优雅退出
            logger.info("Input stream closed, exiting gracefully")
            await explorer.stop()
            await agent.scheduler.stop()
            break
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            await explorer.stop()
            break
        except Exception as e:
            logger.exception("Error occurred during interaction")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Agent CLI")
    parser.add_argument('--chat', '-c', type=str, help="One-shot chat message")
    args = parser.parse_args()
    asyncio.run(main(args))