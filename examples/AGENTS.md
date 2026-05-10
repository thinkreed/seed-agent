# 使用示例目录

演示 Seed Agent Loop 系统核心概念的示例脚本。

---

## 示例文件

| 文件 | 描述 |
|------|------|
| `simple_agent.py` | 基础 Agent Loop：LLMGateway 初始化、工具注册、流式输出 |

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置文件 ~/.seed/config.json（API Keys + 模型设置）

# 运行示例
cd <project-root>
python examples/simple_agent.py
```

---

## 核心概念

### LLMGateway 初始化

```python
from src.client import LLMGateway
gateway = LLMGateway("~/.seed/config.json")
```

### AgentLoop 创建

```python
from src.agent_loop import AgentLoop
agent = AgentLoop(gateway=gateway, max_iterations=30)
```

### 工具注册

```python
agent.tools.register("get_time", get_current_time, schema)
```

### 执行模式

| 模式 | 方法 | 用途 |
|------|------|------|
| 流式 | `stream_run()` | 实时响应（UI 场景） |
| 同步 | `run()` | 批处理（完整响应） |

---

## 配置示例

```json
{
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "model": "qwen-turbo"
    }
  },
  "defaultModel": "bailian"
}
```

---

## 相关文档

- 核心引擎：[src/AGENTS.md](../src/AGENTS.md)
- 工具系统：[src/tools/AGENTS.md](../src/tools/AGENTS.md)