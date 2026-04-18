# Module Overview - Usage Examples

This directory contains example scripts that demonstrate how to use the Seed Agent Loop system. The examples are designed to help you understand the core concepts and quickly get started with building AI agents.

The examples showcase key features including LLMGateway initialization, AgentLoop creation, tool registration, and different execution modes (stream run vs regular run).

# Available Examples

## simple_agent.py - Basic agent loop with tool registration

This example demonstrates a minimal agent implementation with the following features:
- Asynchronous execution using asyncio
- LLMGateway initialization from config file
- AgentLoop creation with custom iteration limits
- Custom tool registration and execution
- Streaming output for real-time responses

This is the recommended starting point for understanding the framework.

# Quick Start Guide

## Prerequisites

Before running the examples, ensure you have:

1. **Python 3.8 or higher** installed on your system
2. **Dependencies installed**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configuration file** at `~/.seed/config.json` with your API keys and model settings

## How to Run Examples

Navigate to the project root and run the example:

```bash
cd E:\projects\seed-agent1
python examples/simple_agent.py
```

The example will initialize the LLMGateway, register a custom tool, and run an agent loop that asks "What time is it?"

# Example Breakdown

## LLMGateway Initialization

The LLMGateway provides a unified interface to various LLM providers. It loads configuration from a JSON file:

```python
import os
from src.client import LLMGateway

# Config path should point to your config.json
config_path = os.path.join(os.path.expanduser("~"), ".seed", "config.json")
gateway = LLMGateway(config_path)
```

The configuration file supports multiple model providers and can use environment variables for API keys.

## AgentLoop Creation

The AgentLoop is the core component that manages the agent's execution cycle:

```python
from src.agent_loop import AgentLoop

# Create an agent with the gateway and set iteration limit
agent = AgentLoop(gateway=gateway, max_iterations=2)
```

The `max_iterations` parameter controls how many times the agent can call tools before returning a final response.

## Tool Registration

Tools extend the agent's capabilities by allowing it to interact with external systems:

```python
# Define a tool function
def get_current_time():
    """Get the current time."""
    import datetime
    return datetime.datetime.now().isoformat()

# Register the tool with a schema
agent.tools.register("get_time", get_current_time, {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Get the current time",
        "parameters": {"type": "object", "properties": {}}
    }
})
```

The schema follows the OpenAI tool calling format, allowing the LLM to understand when and how to use each tool.

## Stream Run vs Regular Run

The agent supports two execution modes:

### Streaming Mode

Returns results incrementally as they become available:

```python
async for chunk in agent.stream_run("What time is it?"):
    if chunk['type'] == 'chunk':
        print(chunk['content'], end='', flush=True)
    elif chunk['type'] == 'final':
        print(f"\n[Final: {chunk['content']}]")
```

This is ideal for user interfaces where you want to show responses as they generate.

### Regular Run

Returns the complete result after execution finishes:

```python
result = await agent.run("What time is it?")
print(result)
```

This is simpler and useful for batch processing or when you need the full response at once.

# Extending Examples

## Adding Custom Tools

To add your own tools, create a Python function and register it with the agent:

```python
def my_custom_tool(arg1, arg2):
    """Description of what the tool does."""
    # Your logic here
    return result

# Register with schema
agent.tools.register("tool_name", my_custom_tool, {
    "type": "function",
    "function": {
        "name": "tool_name",
        "description": "Description for the LLM",
        "parameters": {
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "Description"},
                "arg2": {"type": "integer", "description": "Description"}
            },
            "required": ["arg1"]
        }
    }
})
```

## Using Different Models

Modify your `config.json` to switch between model providers:

```json
{
  "models": {
    "openai": {
      "baseUrl": "https://api.openai.com/v1",
      "apiKey": "${OPENAI_API_KEY}",
      "model": "gpt-4"
    },
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "model": "qwen-turbo"
    }
  },
  "defaultModel": "bailian"
}
```

Set the `defaultModel` to choose which provider to use by default.
