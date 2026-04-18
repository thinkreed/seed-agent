"""
定时优化脚本：从 wiki 提取优化点并在 seed-agent 实施
使用方式：Windows Task Scheduler 每20分钟运行一次
"""

import os
import sys
import json
import random
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 路径配置
WIKI_DIR = Path("E:/projects/wiki")
PROJECT_DIR = Path("E:/projects/seed-agent")
LOG_FILE = PROJECT_DIR / ".seed" / "logs" / "optimize.log"
MEMORY_FILE = PROJECT_DIR / ".seed" / "memory" / "optimize_history.json"
PROCESSED_FILE = PROJECT_DIR / ".seed" / "memory" / "processed_wiki.json"

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("optimizer")

# 加载环境变量
load_dotenv(PROJECT_DIR / ".env")
sys.path.insert(0, str(PROJECT_DIR / "src"))


def get_unprocessed_wiki_file() -> Path:
    """获取未处理的 wiki 文档"""
    # 加载已处理列表
    processed = set()
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
            processed = set(json.load(f))

    # 获取所有 md 文件
    all_files = []
    for f in WIKI_DIR.glob("*.md"):
        if not f.name.startswith("."):
            all_files.append(f)
    for subdir in WIKI_DIR.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("."):
            for f in subdir.glob("*.md"):
                all_files.append(f)

    # 筛选未处理
    unprocessed = [f for f in all_files if str(f) not in processed]
    if not unprocessed:
        # 全部处理过，重置
        processed.clear()
        unprocessed = all_files

    return random.choice(unprocessed) if unprocessed else None


def read_wiki_content(file_path: Path) -> str:
    """读取 wiki 文档内容"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 截取关键部分（避免过长）
    max_len = 8000
    if len(content) > max_len:
        content = content[:max_len] + "\n...[内容截断]"
    return content


def mark_processed(file_path: Path):
    """标记文档已处理"""
    processed = set()
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
            processed = set(json.load(f))

    processed.add(str(file_path))

    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(processed), f, ensure_ascii=False)


def record_optimization(wiki_file: str, optimization: str, result: str):
    """记录优化历史"""
    history = []
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)

    history.append({
        "timestamp": datetime.now().isoformat(),
        "wiki_file": wiki_file,
        "optimization": optimization[:500],
        "result": result[:500]
    })

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def call_llm_for_optimization(wiki_content: str, wiki_file: str) -> dict:
    """调用 LLM 分析并生成优化方案"""
    from client import LLMGateway
    from tools import ToolRegistry
    from tools.builtin_tools import register_builtin_tools
    from tools.memory_tools import register_memory_tools
    from tools.skill_loader import register_skill_tools

    # 初始化
    config_path = str(PROJECT_DIR / "config" / "config.json")
    gateway = LLMGateway(config_path)
    tools = ToolRegistry()
    register_builtin_tools(tools)
    register_memory_tools(tools)
    register_skill_tools(tools)

    # 构建 prompt
    system_prompt = f"""你是一个项目优化执行者。

**任务**：从 wiki 文档中提取可优化的设计模式或最佳实践，在 seed-agent 项目中实施一项具体优化。

**项目路径**：{PROJECT_DIR}
**工作目录**：{PROJECT_DIR / ".seed"}

**原则**：
1. 每次只做一项具体的优化
2. 优先选择低风险、高价值的改进
3. 禁止修改 core_principles 和 config 目录
4. 优化完成后简要报告结果

**可用工具**：file_read, file_write, file_edit, code_as_policy, write_memory
"""

    user_prompt = f"""# Wiki 文档分析

**来源**：{wiki_file}
**时间**：{datetime.now().strftime("%Y-%m-%d %H:%M")}

## 文档内容

{wiki_content}

---

请执行：
1. 分析文档，提取关键设计思想或最佳实践
2. 判断是否适用于 seed-agent 项目
3. 选择一项最有价值的优化点
4. 使用工具实施优化
5. 返回 JSON 格式结果：{{"optimization": "优化描述", "result": "执行结果"}}
"""

    # 调用 LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    model_id = gateway.get_active_provider() + "/" + gateway.config.models[gateway.get_active_provider()].models[0].id

    try:
        response = asyncio.run(gateway.chat_completion(model_id, messages, tools=tools.get_schemas()))

        # 提取结果
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")

            # 尝试解析 JSON
            try:
                # 查找 JSON 部分
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(content[json_start:json_end])
                    return result
            except json.JSONDecodeError:
                pass

            return {"optimization": "分析完成", "result": content[:500]}

        return {"optimization": "无响应", "result": "LLM 未返回有效内容"}

    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return {"optimization": "调用失败", "result": str(e)}


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("定时优化任务启动")

    # 获取未处理文档
    wiki_file = get_unprocessed_wiki_file()
    if not wiki_file:
        logger.warning("No wiki files found")
        return

    logger.info(f"Selected wiki file: {wiki_file.name}")

    # 读取内容
    wiki_content = read_wiki_content(wiki_file)

    # 调用 LLM 分析优化
    result = call_llm_for_optimization(wiki_content, wiki_file.name)

    logger.info(f"Optimization: {result.get('optimization', 'N/A')}")
    logger.info(f"Result: {result.get('result', 'N/A')[:200]}...")

    # 记录
    mark_processed(wiki_file)
    record_optimization(wiki_file.name, result.get("optimization", ""), result.get("result", ""))

    logger.info("定时优化任务完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()