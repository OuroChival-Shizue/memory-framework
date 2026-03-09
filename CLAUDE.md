# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An AI-assisted novel writing framework using a dual-agent architecture to manage character state and generate chapters. The system separates state management from content generation to avoid long-context drift.

## Running the Application

```bash
cd memory_framework
python agent_web.py
```

The web UI runs on `http://localhost:5001` with:
- Chapter generation and viewing at `/chapters`
- Character management at `/`
- Schema configuration at `/schema`

**Critical**: `agent_web.py` changes working directory to `memory_framework/` on startup, so all relative paths resolve from there, not the repo root.

## Core Architecture

### Dual-Agent System

Two separate LLM roles in `dual_agent.py`:

1. **StateAgent** - Manages character state through tool calls
   - Reads character state before generation
   - Updates character state after generation
   - Emits structured progress events during updates
   - Never generates prose

2. **ContentAgent** - Generates chapter prose only
   - Receives cleaned context without tool call history
   - No access to state management tools
   - Focuses purely on narrative generation

Flow: `StateAgent.prepare_context()` → `ContentAgent.generate()` → `StateAgent.update_states()`

### Append-Only State Model

Character data in `data/characters/*.json` uses append-only history, not in-place updates.

Each field stores a timeline:

```json
{
  "fields": {
    "location": [
      {"value": "Mount Hua", "chapter": 1, "reason": "initial", "timestamp": "..."},
      {"value": "East City", "chapter": 3, "reason": "tracking enemy", "timestamp": "..."}
    ]
  }
}
```

This enables time-travel state inspection and explicit change tracking.

### V2 Context System

Multi-stage context building for chapter generation:

1. **SummaryManager** (`summary_manager.py`) - Generates and compresses chapter summaries
2. **ContextBuilder** (`context_builder.py`) - Builds layered context (recent chapters detailed, older compressed)
3. **PromptCleaner** (`prompt_cleaner.py`) - Extracts semantic info from tool calls, removes technical noise
4. **StateAgent** - Active querying mode where LLM decides which character states to fetch

## Key Components

| File | Purpose |
|------|---------|
| `dual_agent.py` | StateAgent and ContentAgent implementations |
| `dynamic_state.py` | Append-only character state storage |
| `agent_tools.py` | OpenAI tool definitions and execution |
| `agent_web.py` | Flask web UI with SSE streaming |
| `context_builder.py` | Multi-stage context assembly for generation |
| `summary_manager.py` | Chapter summary generation and compression |
| `schema_manager.py` | Add/remove character schema fields |
| `state_schema.yaml` | Required/optional fields and update rules |

## Data Structure

```
memory_framework/data/
├── characters/*.json    # Append-only character state
├── chapters/*.txt       # Generated chapter text
├── summaries/*.txt      # Chapter summaries for context
└── config.json          # API keys and model config
```

## SSE Progress Streaming

The web UI uses Server-Sent Events for real-time progress. Event types:

- `status` - Top-level status messages
- `agent_note` - Agent reasoning
- `tool_call` - Tool invocation
- `field_update` - Character field changes
- `tool_result` - Tool execution results
- `tool_error` - Tool failures
- `done` - Completion
- `error` - Fatal errors

If you modify event names or payload structure in `dual_agent.py` or `agent_web.py`, update the frontend handlers in the templates.

## Programmatic Usage

```python
from dual_agent import StateAgent, ContentAgent

state_agent = StateAgent(llm_function=your_llm)
content_agent = ContentAgent(llm_function=your_llm)

# Generate chapter
context = state_agent.prepare_context(chapter=1)
content = content_agent.generate(1, context)
state_agent.update_states(content, chapter=1)
```

With progress callbacks:

```python
def on_progress(event: dict):
    print(event)

state_agent = StateAgent(
    llm_function=your_llm,
    progress_callback=on_progress
)
```

## Important Conventions

- All state updates must include `chapter` and `reason` fields
- `get_character()` returns full history, `get_character_latest()` returns current values only
- `state_schema.yaml` defines the authoritative field schema and update rules
- Character state changes are explicit and tool-driven, never implicit
- Web UI does not auto-close progress panels on success (user inspects changes before refresh)

## Design Philosophy

- Append-only JSON history instead of database
- Explicit tool calls instead of hidden state mutation
- Clean separation between prose generation and state management
- SSE for transparent long-running operations
- High token budget (300M+) - prioritize quality over cost
