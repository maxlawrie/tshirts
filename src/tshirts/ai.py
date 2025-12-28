"""AI-powered issue estimation and breakdown."""

import os
import json
from dataclasses import dataclass

import anthropic

from .github_client import Issue


@dataclass
class SubTask:
    """A broken-down sub-task from a larger issue."""
    title: str
    description: str
    size: str


def _get_client() -> anthropic.Anthropic:
    """Get the Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable required")
    return anthropic.Anthropic(api_key=api_key)


def estimate_issue_size(issue: Issue) -> str:
    """Estimate the t-shirt size of an issue using AI.

    Returns one of: XS, S, M, L, XL
    """
    client = _get_client()

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

Respond with ONLY the size (XS, S, M, L, or XL), nothing else."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )

    size = response.content[0].text.strip().upper()

    # Validate response
    if size not in ["XS", "S", "M", "L", "XL"]:
        return "M"  # Default to medium if unclear

    return size


def breakdown_issue(issue: Issue) -> list[SubTask]:
    """Break down an issue into smaller sub-tasks using AI."""
    client = _get_client()

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

Respond with a JSON array of objects with "title", "description", and "size" fields.
Example: [{{"title": "Add login button", "description": "Add a login button to the header component", "size": "S"}}]

Respond with ONLY the JSON array, no other text."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        tasks_data = json.loads(response.content[0].text.strip())
        return [
            SubTask(
                title=task["title"],
                description=task["description"],
                size=task["size"].upper(),
            )
            for task in tasks_data
        ]
    except (json.JSONDecodeError, KeyError):
        # Return a single task if parsing fails
        return [
            SubTask(
                title=f"Implement: {issue.title}",
                description=issue.body,
                size="M",
            )
        ]
