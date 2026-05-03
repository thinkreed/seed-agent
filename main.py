import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path to allow imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Setup cross-platform logging to ~/.seed/logs with daily rotation
LOG_DIR = Path(os.path.expanduser("~")) / ".seed" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

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

# 初始化 OpenTelemetry 可观测性
try:
    from observability import setup_observability, is_initialized, shutdown_observability  # noqa: E402
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not otlp_endpoint:
        otlp_endpoint = "http://localhost:4318"
    observability_enabled = os.getenv("OTEL_ENABLED", "true").lower().strip() == "true"

    if observability_enabled and not is_initialized():
        setup_observability(
            service_name="seed-agent",
            otlp_endpoint=otlp_endpoint,
            enabled=True
        )
        logger.info(f"Observability initialized: endpoint={otlp_endpoint}")
except ImportError:
    logger.warning("OpenTelemetry not installed, observability disabled")
    # 定义 dummy shutdown 函数
    def shutdown_observability(): pass
except Exception:
    logger.warning("Failed to initialize observability")
    def shutdown_observability(): pass

from agent_loop import AgentLoop  # noqa: E402
from client import LLMGateway  # noqa: E402
from autonomous import AutonomousExplorer  # noqa: E402
from tools.ask_user_types import AskUserResult, AskUserRequest, UserResponse  # noqa: E402

# 凭证安全模块
try:
    from security.credential_vault import CredentialVault  # noqa: E402
    from security.credential_proxy import CredentialProxy  # noqa: E402
    _CREDENTIAL_SECURITY_AVAILABLE = True
except ImportError:
    CredentialVault = None  # type: ignore[misc,assignment]
    CredentialProxy = None  # type: ignore[misc,assignment]
    _CREDENTIAL_SECURITY_AVAILABLE = False

# 全局状态
_shutdown_in_progress = False
_ctrl_c_count = 0
_last_ctrl_c_time = 0


def on_autonomous_complete(response: str):
    """自主探索完成回调"""
    print("\n[自主探索完成] " + "-" * 40)
    print(response[:500] if len(response) > 500 else response)
    print("-" * 50 + "\nYou: ", end="", flush=True)


async def async_input(prompt: str) -> str:
    """异步输入函数"""
    return await asyncio.to_thread(input, prompt)


def parse_user_answer(request: dict[str, Any], answer: str) -> AskUserResult:
    """解析用户输入为结构化响应

    Args:
        request: Ask User 请求
        answer: 用户输入字符串

    Returns:
        AskUserResult 结构化响应
    """
    request_id = request.get("request_id", "unknown")
    questions = request.get("questions", [])
    responses = []

    # 检查取消
    if answer.lower() in ("cancel", "取消", "c"):
        return AskUserResult.cancelled_result(request_id)

    # 简单情况：单个问题
    if len(questions) <= 1:
        q = questions[0] if questions else {}
        options = q.get("options", [])
        multi_select = q.get("multi_select", False)

        # 尝试匹配选项编号
        selected = []
        custom_input = None

        # 处理多选（逗号分隔）
        if multi_select:
            parts = answer.split(",")
            for part in parts:
                part = part.strip()
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(options):
                        opt_val = options[idx].get("value") or options[idx].get("label")
                        selected.append(opt_val)
                    else:
                        # 自定义输入
                        selected.append(part)
                        custom_input = part
                except ValueError:
                    # 自定义输入
                    selected.append(part)
                    custom_input = part
        else:
            # 单选
            try:
                idx = int(answer) - 1
                if 0 <= idx < len(options):
                    opt_val = options[idx].get("value") or options[idx].get("label")
                    selected.append(opt_val)
                else:
                    selected.append(answer)
                    custom_input = answer
            except ValueError:
                selected.append(answer)
                custom_input = answer

        responses.append(UserResponse(
            question_id="0",
            selected=selected,
            custom_input=custom_input,
        ))

    else:
        # 多问题情况
        for i, q in enumerate(questions):
            # 简化处理：假设用户按顺序回答
            options = q.get("options", [])

            try:
                idx = int(answer.split()[i]) - 1 if i < len(answer.split()) else 0
                if 0 <= idx < len(options):
                    opt_val = options[idx].get("value") or options[idx].get("label")
                    responses.append(UserResponse(question_id=str(i), selected=[opt_val]))
                else:
                    responses.append(UserResponse(question_id=str(i), selected=[options[0].get("label")]))
            except (ValueError, IndexError):
                # 默认选择第一个选项
                if options:
                    responses.append(UserResponse(question_id=str(i), selected=[options[0].get("label")]))

    return AskUserResult(request_id=request_id, responses=responses)


async def handle_user_question(
    agent: AgentLoop,
    request: dict[str, Any]
) -> None:
    """处理 Ask User 等待

    Args:
        agent: AgentLoop 实例
        request: Ask User 请求
    """
    questions = request.get("questions", [])

    print("\n[Agent asks:]")
    for i, q in enumerate(questions):
        print(f"  {i+1}. {q.get('question', '')}")
        options = q.get("options", [])
        for j, opt in enumerate(options):
            label = opt.get("label", "")
            desc = opt.get("description", "")
            if desc:
                print(f"     [{j+1}] {label} - {desc}")
            else:
                print(f"     [{j+1}] {label}")

        if q.get("multi_select"):
            print("     (多选：用逗号分隔，如 '1,2,3')")

    # 获取用户响应
    try:
        if len(questions) == 1 and len(questions[0].get("options", [])) <= 4:
            # 简单确认 - 快速处理
            answer = await async_input("Your choice (number or custom): ")
        else:
            # 多问题 - 详细处理
            answer = await async_input("Your answer: ")

        # 解析响应
        response = parse_user_answer(request, answer)

        # 注入响应
        agent.inject_user_input(response)

        if response.cancelled:
            print("[Cancelled by user]")
        else:
            print(f"[Selected: {response.get_selected_values()}]")

    except EOFError:
        # stdin 关闭，取消当前执行
        agent.inject_user_input(AskUserResult.cancelled_result(request.get("request_id", "unknown")))
        print("[Input stream closed, cancelled]")


async def graceful_shutdown(
    agent: AgentLoop,
    explorer: AutonomousExplorer,
    reason: str = "signal"
) -> None:
    """优雅关闭

    参考 qwen-code 的 acpAgent.ts 实现

    Args:
        agent: AgentLoop 实例
        explorer: AutonomousExplorer 实例
        reason: 关闭原因
    """
    global _shutdown_in_progress
    if _shutdown_in_progress:
        return
    _shutdown_in_progress = True

    print(f"\n[Shutting down: {reason}]")

    # 1. 取消当前执行
    agent.cancel_current_execution()

    # 2. 停止自主探索
    await explorer.stop()

    # 3. 停止定时任务
    await agent.scheduler.stop()

    # 4. 保存会话状态
    agent.session.record_session_end(reason)

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
        try:
            agent.sandbox.cleanup()
        except Exception as e:
            logger.warning(f"Sandbox cleanup error: {e}")


def setup_signal_handlers(
    agent: AgentLoop,
    explorer: AutonomousExplorer,
    loop: asyncio.AbstractEventLoop
) -> None:
    """设置信号处理器

    Args:
        agent: AgentLoop 实例
        explorer: AutonomousExplorer 实例
        loop: 事件循环
    """
    def handle_sigterm():
        asyncio.create_task(graceful_shutdown(agent, explorer, "SIGTERM"))

    def handle_sigint():
        asyncio.create_task(graceful_shutdown(agent, explorer, "SIGINT"))

    # Unix 信号处理
    if hasattr(signal, 'SIGTERM'):
        try:
            loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
        except (NotImplementedError, OSError):
            # Windows 或不支持
            signal.signal(signal.SIGTERM, lambda s, f: handle_sigterm())

    if hasattr(signal, 'SIGINT'):
        try:
            loop.add_signal_handler(signal.SIGINT, handle_sigint)
        except (NotImplementedError, OSError):
            # Windows 或不支持
            signal.signal(signal.SIGINT, lambda s, f: handle_sigint())

    # Windows 特殊处理
    if os.name == 'nt':
        try:
            # Windows 使用不同机制
            loop.add_signal_handler(signal.SIGINT, handle_sigint)
        except NotImplementedError:
            pass


async def interactive_loop(agent: AgentLoop, explorer: AutonomousExplorer) -> None:
    """交互式主循环（支持 Ask User 和 Ctrl+C）

    Args:
        agent: AgentLoop 实例
        explorer: AutonomousExplorer 实例
    """
    global _ctrl_c_count, _last_ctrl_c_time

    loop = asyncio.get_event_loop()
    setup_signal_handlers(agent, explorer, loop)

    print("Agent initialized successfully. Type 'exit' to quit.\n")
    print("Starting interactive loop...")
    print("  - Ctrl+C once: cancel current execution")
    print("  - Ctrl+C twice (within 2s): exit agent\n")

    while True:
        try:
            # 获取用户输入
            user_input = await async_input("You: ")
            _ctrl_c_count = 0  # 重置 Ctrl+C 计数

            if user_input.lower() in ('exit', 'quit'):
                await graceful_shutdown(agent, explorer, "user_exit")
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

                chunk_type = chunk.get("type")

                if chunk_type == "chunk":
                    print(chunk["content"], end="", flush=True)
                elif chunk_type == "tool_start":
                    print(f"\n  [Tool: {chunk['tool_name']}]...", end="", flush=True)
                elif chunk_type == "tool_end":
                    # 工具结果可能很长，截断显示
                    result = chunk.get("result", "")
                    if len(result) > 100:
                        result = result[:100] + "..."
                    print(f" done", end="", flush=True)
                elif chunk_type == "awaiting_user_input":
                    # 处理 Ask User 等待
                    await handle_user_question(agent, chunk["request"])
                elif chunk_type == "cancelled":
                    print(f"\n[Cancelled: {chunk.get('reason', 'unknown')}]")
                elif chunk_type == "final":
                    print()  # 响应结束换行
                elif chunk_type == "error":
                    print(f"\n[Error: {chunk.get('content', 'unknown')}]")

            print("-" * 50)  # 分隔符

        except EOFError:
            # stdin 关闭（如管道输入结束），优雅退出
            logger.info("Input stream closed, exiting gracefully")
            await graceful_shutdown(agent, explorer, "eof")
            break

        except KeyboardInterrupt:
            # Ctrl+C 处理
            now = time.time()
            if now - _last_ctrl_c_time < 2.0:  # 2秒内第二次
                # 双击 Ctrl+C - 退出
                await graceful_shutdown(agent, explorer, "ctrl_c_double")
                break
            else:
                # 第一次 Ctrl+C - 取消当前执行
                _ctrl_c_count = 1
                _last_ctrl_c_time = now
                agent.cancel_current_execution()
                print("\n[Execution cancelled. Press Ctrl+C again within 2s to exit.]")
                continue

        except Exception:
            logger.exception("Error occurred during interaction")


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

    # Create PID file for abnormal exit detection
    pid_file = os.path.join(os.path.dirname(__file__), 'tasks', 'seed_agent.pid')
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))

    # Register cleanup on exit
    import atexit
    def remove_pid():
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass
    atexit.register(remove_pid)

    # 启动前诊断检查（可选，使用 --no-check 跳过）
    if not args or not getattr(args, 'no_check', False):
        try:
            seed_dir = Path(os.path.expanduser("~")) / ".seed"
            diag_script = seed_dir / "scripts" / "diagnose_seed_agent.py"
            if diag_script.exists():
                import subprocess
                result = subprocess.run(
                    ['python', str(diag_script), '--json', '-q'],
                    capture_output=True, text=True, encoding='utf-8',
                    cwd=str(seed_dir), timeout=60
                )
                if result.returncode == 0:
                    import json as _json
                    report = _json.loads(result.stdout)
                    summary = report.get('summary', {})
                    failed = summary.get('failed', 0)
                    warned = summary.get('warned', 0)
                    if failed > 0:
                        print(f"  ⚠️  诊断发现 {failed} 个问题，建议运行修复:")
                        print(f"     python {seed_dir}/scripts/diagnose_seed_agent.py --fix")
                        for r in report.get('results', []):
                            if r['status'] == 'FAIL':
                                print(f"     - [{r['severity']}] {r['id']}: {r['name']}")
                    elif warned > 0:
                        print(f"  ℹ️  诊断发现 {warned} 个警告")
                    else:
                        print(f"  ✅ 诊断通过 ({summary.get('passed', 0)} 项)")
        except Exception:
            logger.warning("Pre-start diagnosis skipped")

    try:
        # 初始化凭证安全组件（如果可用）
        vault = None
        credential_proxy = None
        if _CREDENTIAL_SECURITY_AVAILABLE:
            try:
                vault = CredentialVault(auto_generate_key=True)
                credential_proxy = CredentialProxy(vault)
                logger.info("CredentialVault initialized for secure API key storage")
            except Exception as e:
                logger.warning(f"Failed to initialize CredentialVault: {e}")
                vault = None
                credential_proxy = None

        # 初始化网关和 Agent
        gateway = LLMGateway(config_path, vault=vault, credential_proxy=credential_proxy)
        agent = AgentLoop(gateway=gateway, system_prompt=system_prompt)

        # One-shot chat mode：不启动自主探索
        if args and args.chat:
            try:
                response = await agent.run(args.chat)
                print(response)
            except Exception:
                logger.exception("One-shot chat failed")
            return

        # 交互模式：启动自主探索监控和定时任务调度
        await explorer.start()
        await agent.scheduler.start()

        # 进入交互循环
        await interactive_loop(agent, explorer)

    except Exception:
        logger.exception("Failed to initialize agent")
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Agent CLI")
    parser.add_argument('--chat', '-c', type=str, help="One-shot chat message")
    parser.add_argument('--no-check', action='store_true', help="Skip pre-start diagnosis check")
    args = parser.parse_args()

    try:
        asyncio.run(main(args))
    finally:
        # 程序退出时强制 flush 所有 pending traces
        shutdown_observability()