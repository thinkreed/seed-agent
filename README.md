# Seed Agent Loop

A modular, asynchronous Agent Loop system supporting multi-provider LLM configuration, tool use, and streaming output. The system is designed as a physics-based autonomous evolution executor capable of independent reasoning, memory persistence, and self-improvement through exploration.

## Project Structure

```
seed-agent/
├── config/                  # Configuration files and AGENTS.md
├── core_principles/         # System prompts and core principles
├── docs/                    # Documentation
├── examples/                # Usage examples and AGENTS.md
├── memory/                  # Memory system (L1-L4) and AGENTS.md
├── auto/                    # Autonomous exploration module and AGENTS.md
├── src/                     # Core engine and AGENTS.md
│   ├── __init__.py
│   ├── agent_loop.py        # Main agent loop logic
│   ├── client.py            # LLM Gateway (OpenAI compatible)
│   ├── models.py            # Pydantic configuration models
│   └── tools/               # Tool registry and AGENTS.md
├── main.py                  # Interactive CLI entry point
└── requirements.txt         # Dependencies
```

For detailed module documentation, see [Module Documentation](#module-documentation) below.

## Architecture Overview

Seed Agent Loop implements a hierarchical agent architecture with the following core components:

### Agent Loop Engine
The core execution engine (`src/agent_loop.py`) manages the conversation lifecycle, handling message history, tool invocation, and response streaming. It maintains a state machine that tracks agent thinking, tool execution, and result processing phases.

### Multi-Provider Gateway
The client layer (`src/client.py`) provides a unified OpenAI-compatible interface supporting multiple LLM providers. Configuration-driven provider selection allows seamless switching between different models without code changes.

### Memory Hierarchy
The system implements a four-tier memory architecture:

- **L1 (Working Memory)**: Current conversation context, active tool states
- **L2 (Episodic Memory)**: Session-level history and interaction patterns
- **L3 (Semantic Memory)**: Learned knowledge, patterns, and abstractions
- **L4 (World Memory)**: Cross-session knowledge, project-specific insights

See [memory/AGENTS.md](memory/AGENTS.md) for detailed memory system documentation.

### Autonomous Exploration
The autonomous exploration module (`auto/`) enables the agent to independently discover solutions, analyze failures, and evolve strategies. This feature allows the system to:
- Detect and diagnose execution failures
- Explore alternative approaches when initial attempts fail
- Record and leverage learned experiences

See [auto/AGENTS.md](auto/AGENTS.md) for detailed exploration documentation.

### Tool System
The tool registry (`src/tools/`) provides extensibility for agent capabilities. Tools are defined using a declarative schema and can include:
- File system operations
- Code execution and analysis
- Web research and information retrieval
- Custom domain-specific actions

See [src/tools/AGENTS.md](src/tools/AGENTS.md) for tool development guidelines.

## Memory System

The memory system provides persistent context across sessions, enabling the agent to accumulate knowledge and improve over time. Each tier serves a specific purpose:

| Tier | Name | Purpose | Persistence |
|------|------|---------|-------------|
| L1 | Working Memory | Active conversation context | Session |
| L2 | Episodic Memory | Interaction history | Session |
| L3 | Semantic Memory | Learned patterns | Persistent |
| L4 | World Memory | Cross-session knowledge | Persistent |

The memory system automatically manages data flow between tiers, with L3 and L4 providing long-term storage backed by file-based persistence.

See [memory/AGENTS.md](memory/AGENTS.md) for implementation details.

## Autonomous Exploration

When the agent encounters failures or uncertainties, the autonomous exploration system activates to:

1. **Failure Detection**: Identify when an operation fails or produces unexpected results
2. **Root Cause Analysis**: Explore potential causes through targeted probing
3. **Strategy Evolution**: Develop and test alternative approaches
4. **Knowledge Recording**: Store discovered patterns for future use

This system implements a three-strike rule for failure recovery:
- First failure: Retry with same approach
- Second failure: Update strategy based on error analysis
- Third failure: Propose alternative solutions or consult user

See [auto/AGENTS.md](auto/AGENTS.md) for detailed documentation.

## Tool System

Tools extend the agent's capabilities beyond text generation. The tool system provides:

- **Schema-Driven Definition**: Tools declare their inputs, outputs, and behavior
- **Sandboxed Execution**: Tools run in controlled environments
- **Result Processing**: Tool outputs feed back into the agent's context
- **Extensibility**: New tools can be added without modifying core logic

Example tool definition:
```python
@tool()
def read_file(path: str) -> str:
    """Read contents of a file."""
    with open(path, 'r') as f:
        return f.read()
```

See [src/tools/AGENTS.md](src/tools/AGENTS.md) for creating custom tools.

## Configuration Guide

### Basic Configuration

Edit `config/config.json` to configure your API keys and model providers:

```json
{
  "models": {
    "bailian": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "model": "qwen-coder-plus",
      "temperature": 0.7
    }
  },
  "defaultModel": "bailian"
}
```

*API keys can be environment variables (e.g., `${BAILIAN_API_KEY}`) or plain strings.*

### Model Providers

The system supports any OpenAI-compatible API. Configure multiple providers for fallback:

```json
{
  "models": {
    "primary": {
      "baseUrl": "https://api.openai.com/v1",
      "apiKey": "${OPENAI_API_KEY}",
      "model": "gpt-4"
    },
    "fallback": {
      "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "${BAILIAN_API_KEY}",
      "model": "qwen-coder-plus"
    }
  }
}
```

### Important Constraint

**Do not modify `config/config.json` directly.** The configuration file is fully set up and should not be altered. If you need custom configuration, create a separate configuration file and load it programmatically.

See [config/AGENTS.md](config/AGENTS.md) for advanced configuration options.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**:
   The system is pre-configured in `config/config.json`. API keys should be provided via environment variables.

3. **Run Interactive Mode**:
   ```bash
   python main.py
   ```

## Usage Example

See `examples/simple_agent.py` for a programmatic example demonstrating:
- Tool invocation
- Streaming responses
- Multi-turn conversations
- Custom tool registration

## Module Documentation

Each module has dedicated documentation in its AGENTS.md file:

| Module | Description | Documentation |
|--------|-------------|---------------|
| Core Engine | Agent loop, client, models | [src/AGENTS.md](src/AGENTS.md) |
| Tools | Tool registry and development | [src/tools/AGENTS.md](src/tools/AGENTS.md) |
| Configuration | Config management | [config/AGENTS.md](config/AGENTS.md) |
| Core Principles | System prompts | [core_principles/AGENTS.md](core_principles/AGENTS.md) |
| Examples | Usage examples | [examples/AGENTS.md](examples/AGENTS.md) |
| Memory | L1-L4 memory system | [memory/AGENTS.md](memory/AGENTS.md) |
| Autonomous | Self-exploration module | [auto/AGENTS.md](auto/AGENTS.md) |

## Acknowledgments

Special thanks to [GenericAgent](https://github.com/lsdefine/GenericAgent) for inspiration to this project.
