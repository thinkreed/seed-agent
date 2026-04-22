# Module Overview - Autonomous Exploration SOP

This module enables the agent to perform autonomous exploration tasks when idle. It monitors user activity and automatically triggers the Self-Driven Exploration SOP (Standard Operating Procedure) after detecting prolonged inactivity. The system operates as a physics-level, fully capable evolutionary executor that proactively identifies and executes tasks without waiting for explicit user instructions.

The autonomous exploration framework is designed around two core principles: execution viability and evolutionary沉淀 (knowledge accumulation/refinement). The agent continuously evaluates opportunities for task execution and knowledge building, ensuring productive use of idle time while advancing its capabilities.

## Ralph Loop Integration

The AutonomousExplorer is now enhanced with Ralph Loop mechanisms for long-cycle deterministic task execution:

### Completion Promise Detection

External completion markers drive task exit, ensuring objective task completion:
- Checks `~/.seed/completion_promise` file for completion tokens (DONE, COMPLETE, TASK_FINISHED)
- Automatically clears marker on detection
- Prevents infinite loops through external verification

### Context Reset Mechanism

Periodic history reset prevents drift in long-running tasks:
- **Reset Interval**: Every 5 iterations (configurable via `CONTEXT_RESET_INTERVAL`)
- **Critical Context Extraction**: Preserves key decisions and findings from previous iterations
- **Fresh Context Injection**: Re-injects summarized state for continuity

### State Persistence

Task state saved to filesystem for crash recovery:
- State file: `~/.seed/ralph_state.json`
- Contains: iteration count, start time, last response, timestamp
- Enables resumption after process crash

### Safety Limits

Maximum iteration and duration protection:
- **Max Iterations**: 1000 (configurable via `RALPH_MAX_ITERATIONS`)
- **Max Duration**: 8 hours (configurable via `RALPH_MAX_DURATION`)
- Automatic exit with status report when limits reached

# Trigger Conditions

The autonomous exploration activates when specific conditions are met:

**Idle Timeout**: The system monitors for a continuous idle period of **1 hour** (IDLE_TIMEOUT = 60 * 60 seconds). This value is configured as a class constant in the AutonomousExplorer class.

**Monitoring Mechanism**: The AutonomousExplorer class runs an idle monitoring loop that checks the time since the last user activity every 30 seconds. When the idle duration exceeds the threshold, the exploration workflow is triggered automatically.

**Activity Recording**: User activities reset the idle timer via the record_activity() method. This ensures the autonomous mode only engages during genuine idle periods.

# SOP Workflow

The autonomous exploration follows a structured workflow:

**1. Check TODO.md for Pending Tasks**

The system first examines the TODO.md file in the seed directory to determine whether executable tasks exist.

**2. Execute or Enter Planning Mode**

- **If TODO exists**: The agent enters execution mode, processing each TODO item sequentially. Before execution, the agent performs reasoning within <thinking> tags to plan the approach.
  
- **If no TODO exists**: The agent enters planning mode, which involves:
  - Critically reviewing history.md and working memory to identify low-value operations
  - Reflecting on optimization opportunities
  - Generating 5-7 new TODO items with the format: `[ ] Type | Goal | Acceptance Criteria | Expected沉淀`
  - Updating the TODO.md file for future execution

**3. Value Formula**

Every task is evaluated using the formula:

> **实际执行可落地性 × 进化沉淀价值**

(Execution Viability × Evolutionary Knowledge Value)

This ensures that only tasks with practical execution potential and meaningful knowledge accumulation are pursued.

# Key Principles

The autonomous exploration adheres to these foundational principles:

**No Shirking (不推诿)**: The agent never refuses tasks with "cannot operate." When no solution exists, alternative suggestions must be provided.

**Logical Approach (有逻辑)**: Every operation requires prior reasoning within <thinking> tags. Blind execution is prohibited.

**Evolution Focus (重沉淀)**: After task completion, working memory must be updated. When conditions are met, the agent must call experience refinement tools before concluding.

**Failure Escalation Protocol**: When encountering failures:
1. First attempt: Retry the operation
2. Second attempt: Probe for root causes and adjust strategy
3. Third attempt: Switch approach or consult the user

# Integration

The autonomous exploration module is integrated into the agent system as follows:

**AutonomousExplorer Class**: Located in `src/autonomous.py`, this class manages the idle monitoring loop and task execution. Key components include:
- `_idle_monitor_loop()`: Checks idle time every 30 seconds
- `_execute_autonomous_task()`: Runs the exploration workflow with Ralph Loop enhanced iteration
- `_build_autonomous_prompt()`: Constructs the complete prompt including system prompt, skills, and SOP
- `_check_completion_promise()`: Ralph Loop mechanism for external completion detection
- `_check_safety_limits()`: Ralph Loop safety protection (iterations/duration)
- `_reset_context_if_needed()`: Ralph Loop context reset for drift prevention
- `_persist_state()`: Ralph Loop state persistence for crash recovery

**Ralph Loop Configuration** (in autonomous.py):
- `COMPLETION_PROMISE_FILE`: `~/.seed/completion_promise`
- `COMPLETION_PROMISE_TOKENS`: ["DONE", "COMPLETE", "TASK_FINISHED"]
- `CONTEXT_RESET_ENABLED`: True (default)
- `CONTEXT_RESET_INTERVAL`: 5 (iterations)
- `RALPH_MAX_ITERATIONS`: 1000
- `RALPH_MAX_DURATION`: 8 * 60 * 60 (8 hours)

**SOP Document Loading**: The SOP is loaded from `auto/自主探索 SOP.md` during initialization. This document contains the complete guidelines for autonomous task execution.

**Prompt Construction**: The system builds comprehensive prompts that combine:
- Base system prompt from the agent
- Skills prompt from the skill loader
- Full SOP content
- Current TODO status and task instructions

# Files in this Module

| File | Description |
|------|-------------|
| 自主探索 SOP.md | The autonomous exploration SOP document (Chinese filename) - contains detailed workflow, principles, and guidelines |
| src/autonomous.py | Implementation of the AutonomousExplorer class with Ralph Loop integration |
| src/ralph_loop.py | Ralph Loop implementation for long-cycle deterministic task execution |
| src/tools/ralph_tools.py | Tools for Ralph Loop management (start, stop, status check, completion markers) |
| docs/long_cycle_loop_enhancement_design.md | Ralph Loop design documentation |
| docs/ralph_loop.md | Ralph Loop concept documentation |
