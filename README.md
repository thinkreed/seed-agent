# Seed Agent Loop

A modular, asynchronous Agent Loop system supporting multi-provider LLM configuration, tool use, and streaming output.

## Project Structure

```
seed-agent/
├── config/
│   └── config.json      # Model and provider configuration
├── docs/
│   └── ...
├── examples/
│   └── simple_agent.py  # Usage example
├── src/
│   ├── __init__.py
│   ├── agent_loop.py    # Main agent loop logic
│   ├── client.py        # LLM Gateway (OpenAI compatible)
│   ├── models.py        # Pydantic configuration models
│   └── tools/
│       └── __init__.py  # Tool registry
├── main.py              # Interactive CLI entry point
└── requirements.txt     # Dependencies
```

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**:
   Edit `config/config.json` to set your API keys and model providers.
   ```json
   {
     "models": {
       "bailian": {
         "baseUrl": "https://coding.dashscope.aliyuncs.com/v1",
         "apiKey": "${BAILIAN_API_KEY}",
         ...
       }
     }
   }
   ```
   *Keys can be environment variables (e.g., `${BAILIAN_API_KEY}`) or plain strings.*

3. **Run Interactive Mode**:
   ```bash
   python main.py
   ```

## Usage Example

See `examples/simple_agent.py` for a programmatic example using tools.

## Acknowledgments

Special thanks to [GenericAgent](https://github.com/lsdefine/GenericAgent) for inspiration and contributions to this project.