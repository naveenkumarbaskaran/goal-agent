# goal-agent-ai

An AI-powered goal-tracking agent built on the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (Claude `claude-sonnet-4-6`).

Give it a high-level goal like *"Run a marathon in 6 months"* and the agent will:

- Decompose it into 4-8 measurable **milestones** spread over the timeline
- Generate 3-5 concrete **weekly tasks** per milestone
- Persist everything in a local `goals.json` file
- Provide a daily **check-in** with progress and nudges
- Track **completion rate** across all goals

---

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)

---

## Installation

```bash
# From source
pip install -e .

# Or install dependencies directly
pip install anthropic click rich
```

Export your API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Usage

### Add a goal

```bash
goal-agent add "Run a marathon in 6 months"
```

The agent calls Claude, which:
1. Fetches today's date
2. Reads (or creates) `goals.json`
3. Decomposes the goal into milestones and weekly tasks
4. Writes the plan back to `goals.json`
5. Prints a motivating summary

### Daily check-in

```bash
goal-agent checkin
```

Reports which tasks are due this week, your current progress percentage, and an encouraging nudge.

### View status

```bash
goal-agent status
```

Displays a progress table for every goal (tasks done / total, completion %).

### Complete a task

```bash
# First, find the task ID
goal-agent list-tasks --pending-only

# Then mark it done
goal-agent complete <task_id>
```

### Use a custom goals file

```bash
goal-agent --goals-file ~/my-goals.json status
```

---

## Project Structure

```
goal_agent/
  __init__.py    — package exports
  agent.py       — GoalAgent: Claude + tool-use agentic loop
  tracker.py     — GoalTracker: CRUD + progress for goals.json
  cli.py         — Click CLI: add, checkin, status, complete, list-tasks
pyproject.toml
README.md
```

### How the agentic loop works

`GoalAgent._run()` implements a standard tool-use loop:

1. Send the user message to Claude with three tool definitions.
2. If Claude responds with `tool_use` blocks, dispatch each locally (`read_file`, `write_file`, `get_todays_date`).
3. Feed all tool results back as a `user` turn.
4. Repeat until `stop_reason == "end_turn"` (no more tool calls).

### Tools available to Claude

| Tool | Description |
|---|---|
| `read_file(path)` | Read any local file (typically `goals.json`) |
| `write_file(path, content)` | Write/overwrite a file |
| `get_todays_date()` | Return today's ISO-8601 date |

---

## goals.json schema

```json
{
  "goals": [
    {
      "id": "<uuid>",
      "title": "Run a marathon in 6 months",
      "description": "...",
      "target_date": "2026-12-03",
      "created_at": "2026-06-03",
      "milestones": [
        { "id": "<uuid>", "title": "Complete first 5K run", "week": 2, "completed": false }
      ],
      "tasks": [
        {
          "id": "<uuid>",
          "title": "Run 3 x 20-minute easy jogs",
          "milestone_id": "<uuid>",
          "week": 1,
          "completed": false,
          "completed_at": null
        }
      ]
    }
  ]
}
```

---

## Development

```bash
# Install in editable mode with dev deps
pip install -e .

# Run the CLI directly
python -m goal_agent.cli add "Learn Spanish in 3 months"
```

---

## License

MIT
