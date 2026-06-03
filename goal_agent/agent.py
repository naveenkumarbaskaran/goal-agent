"""GoalAgent: uses Claude (claude-sonnet-4-6) to decompose goals and run check-ins."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

from .tracker import GoalTracker

MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Tool implementations (executed locally)
# ---------------------------------------------------------------------------


def _read_file(path: str) -> str:
    """Read the contents of a file and return it as a string."""
    p = Path(path)
    if not p.exists():
        return f"ERROR: file not found: {path}"
    return p.read_text(encoding="utf-8")


def _write_file(path: str, content: str) -> str:
    """Write *content* to *path*, creating parent directories as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} chars to {path}"


def _get_todays_date() -> str:
    """Return today's date as an ISO-8601 string (YYYY-MM-DD)."""
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Tool schemas (JSON Schema for the Messages API)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read the entire contents of a file from the local filesystem. "
            "Use this to inspect goals.json or any other data file before making decisions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file, overwriting it if it already exists. "
            "Use this to persist updated goals.json after decomposing a goal or recording progress."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "get_todays_date",
        "description": "Return today's date in YYYY-MM-DD format. Call this whenever you need the current date.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


def _dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    if name == "read_file":
        return _read_file(tool_input["path"])
    if name == "write_file":
        return _write_file(tool_input["path"], tool_input["content"])
    if name == "get_todays_date":
        return _get_todays_date()
    return f"ERROR: unknown tool '{name}'"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are GoalAgent, an AI assistant that helps people achieve ambitious goals by breaking them 
down into concrete, time-bound milestones and weekly tasks.

You have access to three tools:
- read_file(path)        — read any file, especially goals.json
- write_file(path, content) — write / update files
- get_todays_date()     — get today's ISO date

The canonical data store is goals.json (in the current working directory). Its schema is:

{
  "goals": [
    {
      "id": "<uuid>",
      "title": "<goal title>",
      "description": "<free-text description>",
      "target_date": "YYYY-MM-DD",
      "created_at": "YYYY-MM-DD",
      "milestones": [
        {
          "id": "<uuid>",
          "title": "<milestone title>",
          "week": <int — week number from start>,
          "completed": false
        }
      ],
      "tasks": [
        {
          "id": "<uuid>",
          "title": "<task title>",
          "milestone_id": "<milestone uuid>",
          "week": <int>,
          "completed": false,
          "completed_at": null
        }
      ]
    }
  ]
}

When asked to add a goal:
1. Call get_todays_date() to learn today's date.
2. Call read_file("goals.json") to load existing data (create empty structure if file absent).
3. Decompose the goal into 4-8 measurable milestones spanning the full duration.
4. For each milestone create 3-5 concrete weekly tasks (specific, actionable, completable in a week).
5. Write the updated JSON back with write_file("goals.json", ...).
6. Summarise the plan to the user in a friendly, motivating way.

When asked for a daily check-in:
1. Call get_todays_date().
2. Read goals.json.
3. Identify tasks due this week for each active goal.
4. Report progress %, upcoming tasks, and an encouraging nudge.

When asked for status:
1. Read goals.json.
2. For each goal compute: completed tasks / total tasks * 100.
3. Present a clean summary table.

Always think step-by-step. Produce well-formed JSON when writing goals.json.
"""


# ---------------------------------------------------------------------------
# GoalAgent class
# ---------------------------------------------------------------------------


class GoalAgent:
    """Orchestrates Claude + local tools to manage goals."""

    def __init__(self, goals_path: str = "goals.json", api_key: str | None = None) -> None:
        self.goals_path = goals_path
        self.tracker = GoalTracker(goals_path)
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ------------------------------------------------------------------
    # Core agentic loop
    # ------------------------------------------------------------------

    def _run(self, user_message: str) -> str:
        """Send *user_message* to Claude and run the tool-use loop.

        Returns the final text response from the model.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        while True:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )

            # Collect any text blocks from this response
            text_parts: list[str] = []
            tool_use_blocks: list[Any] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            # If there are no tool calls, we are done
            if response.stop_reason == "end_turn" or not tool_use_blocks:
                return "\n".join(text_parts).strip()

            # Append assistant turn (with all content blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Execute every tool call and collect results
            tool_results: list[dict[str, Any]] = []
            for tool_block in tool_use_blocks:
                result = _dispatch_tool(tool_block.name, tool_block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    }
                )

            # Feed results back as a user turn
            messages.append({"role": "user", "content": tool_results})

    # ------------------------------------------------------------------
    # Public methods (thin wrappers around _run)
    # ------------------------------------------------------------------

    def add_goal(self, description: str) -> str:
        """Decompose *description* into milestones + tasks, persist, and return summary."""
        prompt = (
            f"Please add the following goal and build a full milestone/task plan for it:\n\n"
            f"{description}\n\n"
            f"Store everything in {self.goals_path}."
        )
        return self._run(prompt)

    def daily_checkin(self) -> str:
        """Return a personalised check-in prompt for today's tasks."""
        prompt = (
            f"Give me my daily check-in. Read {self.goals_path}, figure out what is due "
            f"this week, report my progress, and send me motivating nudges."
        )
        return self._run(prompt)

    def status(self) -> str:
        """Return a status summary with completion percentages for all goals."""
        prompt = (
            f"Read {self.goals_path} and give me a status summary for all my goals, "
            f"including completion percentages and any overdue tasks."
        )
        return self._run(prompt)

    def complete_task(self, task_id: str) -> str:
        """Mark *task_id* as complete, persist, and return confirmation."""
        prompt = (
            f"Mark task with id '{task_id}' as completed in {self.goals_path}. "
            f"Set completed=true and completed_at to today's date. "
            f"Then confirm what was completed and update my overall progress."
        )
        return self._run(prompt)
