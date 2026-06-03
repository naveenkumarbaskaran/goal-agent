"""GoalTracker: CRUD operations and progress computation for goals.json."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any


class GoalTracker:
    """Read/write goals, milestones, and tasks in a local JSON file.

    All mutating methods immediately persist changes to disk.
    """

    def __init__(self, path: str = "goals.json") -> None:
        self.path = Path(path)
        self._ensure_file()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_file(self) -> None:
        """Create an empty goals.json if it does not exist."""
        if not self.path.exists():
            self.path.write_text(json.dumps({"goals": []}, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Goal CRUD
    # ------------------------------------------------------------------

    def list_goals(self) -> list[dict[str, Any]]:
        """Return all goals (shallow copy)."""
        return self._load()["goals"]

    def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        """Return the goal dict for *goal_id*, or None if not found."""
        for goal in self.list_goals():
            if goal["id"] == goal_id:
                return goal
        return None

    def add_goal(
        self,
        title: str,
        description: str = "",
        target_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a bare goal (no milestones/tasks) and return it."""
        data = self._load()
        goal: dict[str, Any] = {
            "id": self._new_id(),
            "title": title,
            "description": description,
            "target_date": target_date or "",
            "created_at": date.today().isoformat(),
            "milestones": [],
            "tasks": [],
        }
        data["goals"].append(goal)
        self._save(data)
        return goal

    def delete_goal(self, goal_id: str) -> bool:
        """Remove *goal_id*. Returns True if found and removed, False otherwise."""
        data = self._load()
        before = len(data["goals"])
        data["goals"] = [g for g in data["goals"] if g["id"] != goal_id]
        self._save(data)
        return len(data["goals"]) < before

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        goal_id: str | None = None,
        completed: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Return tasks, optionally filtered by goal and/or completion status."""
        tasks: list[dict[str, Any]] = []
        for goal in self.list_goals():
            if goal_id and goal["id"] != goal_id:
                continue
            for task in goal.get("tasks", []):
                if completed is None or task["completed"] == completed:
                    tasks.append({**task, "_goal_title": goal["title"]})
        return tasks

    def get_task(self, task_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Return (goal, task) for *task_id*, or None if not found."""
        for goal in self.list_goals():
            for task in goal.get("tasks", []):
                if task["id"] == task_id:
                    return goal, task
        return None

    def complete_task(self, task_id: str) -> bool:
        """Mark *task_id* complete. Returns True on success."""
        data = self._load()
        for goal in data["goals"]:
            for task in goal.get("tasks", []):
                if task["id"] == task_id:
                    task["completed"] = True
                    task["completed_at"] = datetime.now().isoformat()
                    self._save(data)
                    return True
        return False

    def add_task(
        self,
        goal_id: str,
        title: str,
        milestone_id: str = "",
        week: int = 1,
    ) -> dict[str, Any] | None:
        """Append a task to *goal_id*. Returns the new task dict, or None if goal not found."""
        data = self._load()
        for goal in data["goals"]:
            if goal["id"] == goal_id:
                task: dict[str, Any] = {
                    "id": self._new_id(),
                    "title": title,
                    "milestone_id": milestone_id,
                    "week": week,
                    "completed": False,
                    "completed_at": None,
                }
                goal.setdefault("tasks", []).append(task)
                self._save(data)
                return task
        return None

    # ------------------------------------------------------------------
    # Progress computation
    # ------------------------------------------------------------------

    def progress(self, goal_id: str | None = None) -> dict[str, Any]:
        """Return progress stats.

        If *goal_id* is given, return stats for that goal only.
        Otherwise return an aggregated dict with per-goal breakdown.
        """
        goals = self.list_goals()
        if goal_id:
            goals = [g for g in goals if g["id"] == goal_id]

        results: list[dict[str, Any]] = []
        total_tasks = 0
        total_done = 0

        for goal in goals:
            tasks = goal.get("tasks", [])
            done = sum(1 for t in tasks if t["completed"])
            pct = round(done / len(tasks) * 100, 1) if tasks else 0.0
            results.append(
                {
                    "goal_id": goal["id"],
                    "title": goal["title"],
                    "total_tasks": len(tasks),
                    "completed_tasks": done,
                    "completion_pct": pct,
                    "milestones_total": len(goal.get("milestones", [])),
                    "milestones_done": sum(
                        1 for m in goal.get("milestones", []) if m.get("completed")
                    ),
                }
            )
            total_tasks += len(tasks)
            total_done += done

        overall_pct = round(total_done / total_tasks * 100, 1) if total_tasks else 0.0
        return {
            "goals": results,
            "overall": {
                "total_tasks": total_tasks,
                "completed_tasks": total_done,
                "completion_pct": overall_pct,
            },
        }
