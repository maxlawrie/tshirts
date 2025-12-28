"""AI-powered issue estimation and breakdown."""

import json
import shutil
import subprocess
from dataclasses import dataclass

from .github_client import Issue


def _find_claude() -> str:
    """Find the claude CLI executable."""
    claude = shutil.which("claude")
    if claude:
        return claude
    # Fallback for Windows
    claude_cmd = shutil.which("claude.cmd")
    if claude_cmd:
        return claude_cmd
    raise FileNotFoundError("claude CLI not found. Install it with: npm install -g @anthropic-ai/claude-code")


@dataclass
class SubTask:
    """A broken-down sub-task from a larger issue."""
    title: str
    description: str
    size: str


SIZE_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "size": {
            "type": "string",
            "enum": ["XS", "S", "M", "L", "XL"]
        }
    },
    "required": ["size"]
})

BREAKDOWN_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "size": {"type": "string", "enum": ["XS", "S", "M", "L", "XL"]}
                },
                "required": ["title", "description", "size"]
            }
        }
    },
    "required": ["tasks"]
})


def _call_claude(prompt: str, schema: str | None = None) -> str:
    """Call Claude CLI with a prompt and return the response."""
    claude_path = _find_claude()
    cmd = [claude_path, "-p", "--model", "sonnet"]
    if schema:
        cmd.extend(["--output-format", "json", "--json-schema", schema])

    # Pass prompt via stdin to handle multi-line content properly
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def estimate_issue_size(issue: Issue) -> str:
    """Estimate the t-shirt size of an issue using AI.

    Returns one of: XS, S, M, L, XL
    """
    prompt = f"""Analyze this GitHub issue and estimate its size using t-shirt sizing.

Issue #{issue.number}: {issue.title}

Description:
{issue.body}

Size guide:
- XS: Trivial change, <30 min (typo fix, config change, small tweak)
- S: Small task, 1-2 hours (simple bug fix, small feature, single file change)
- M: Medium task, half day to 1 day (moderate feature, multiple files, some testing)
- L: Large task, 2-3 days (significant feature, refactoring, multiple components)
- XL: Very large, 1+ week (major feature, architectural change, needs breakdown)

Return the estimated size."""

    try:
        response = _call_claude(prompt, SIZE_SCHEMA)
        data = json.loads(response)
        # Extract structured_output from Claude CLI response
        if "structured_output" in data:
            return data["structured_output"].get("size", "M")
        # Fallback: check if size is directly in data
        if "size" in data:
            return data["size"]
        return "M"
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError):
        return "M"


def breakdown_issue(issue: Issue) -> list[SubTask]:
    """Break down an issue into smaller sub-tasks using AI."""
    prompt = f"""Break down this GitHub issue into smaller, actionable sub-tasks.

Issue #{issue.number}: {issue.title}

Description:
{issue.body}

Create 3-7 sub-tasks that together complete this issue. Each sub-task should be:
- Independently implementable
- Small enough to complete in 1-2 days max
- Clear and specific

For each sub-task, estimate its size:
- XS: <30 min
- S: 1-2 hours
- M: half day to 1 day
- L: 2-3 days

Return an array of tasks with title, description, and size."""

    try:
        response = _call_claude(prompt, BREAKDOWN_SCHEMA)
        data = json.loads(response)
        # Extract structured_output from Claude CLI response
        if "structured_output" in data:
            data = data["structured_output"]
        # Get the tasks array from the object
        tasks = data.get("tasks", [])
        return [
            SubTask(
                title=task["title"],
                description=task["description"],
                size=task["size"].upper(),
            )
            for task in tasks
        ]
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, TypeError):
        return [
            SubTask(
                title=f"Implement: {issue.title}",
                description=issue.body,
                size="M",
            )
        ]
