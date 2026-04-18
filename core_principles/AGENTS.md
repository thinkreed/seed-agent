# Module Overview - System Prompts

This module contains the core system prompts that define the agent's behavior, identity, and operational principles. These prompts are loaded at initialization and guide all agent interactions.

# Files in this Module

| File | Description |
|------|-------------|
| `system_prompts_en.md` | English system prompts defining agent behavior |
| `system_prompts_zh.md` | Chinese system prompts defining agent behavior |

# Purpose

The system prompts serve several critical functions:

1. **Defines Agent Identity**: Establishes the agent as a "Physical-Level Omnipotent Evolutionary Executor" with autonomous evolution capabilities.

2. **Establishes Core Permissions**: Documents the agent's permissions including:
   - Physical operations (file reading/writing, script execution)
   - Browser intervention (JS injection, page manipulation)
   - System intervention (environment detection, tool calling)
   - Evolution permissions (recording, experience precipitation)

3. **Defines Action Principles**: Provides guidelines for operation:
   - Deduction before action in `<thinking>` tags
   - Key information detection on failure
   - Failure escalation strategy
   - Autonomous evolution through experience summarization

4. **Sets Working Memory**: Requires recording operation logs, experience databases, and capability lists.

5. **Establishes Core Taboos**: Defines prohibited behaviors to ensure reliable operation.

# Usage

## Loading System Prompts

The system prompts are loaded by `main.py` at initialization:

```python
# Load system prompt
prompt_path = os.path.join(os.path.dirname(__file__), 'core_principles', 'system_prompts_en.md')
system_prompt = None
if os.path.exists(prompt_path):
    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()
```

## Integration with AgentLoop

The loaded prompt is passed to `AgentLoop` as the `system_prompt` parameter:

```python
agent = AgentLoop(gateway=gateway, system_prompt=system_prompt)
```

## Reference

To reference these prompts in code, use the path:
```
core_principles/system_prompts_en.md
```

# IMPORTANT: CONSTRAINT WARNING

**DO NOT MODIFY files in this directory.**

These files define core agent behavior and must remain unchanged. The system prompts establish the fundamental identity, permissions, and operational principles that govern all agent interactions.

Modifying these files could:
- Alter the agent's core identity and purpose
- Change fundamental behavioral constraints
- Break compatibility with other system components that expect specific prompt formats

This constraint is enforced by the root `AGENTS.md` which states: **禁止修改 core_principles目录下的文件** (Do not modify files in the core_principles directory).
