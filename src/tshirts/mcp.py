"""MCP server for tshirts - GitHub issue sizing and breakdown.

Exposes tshirts functionality to LLM clients via the Model Context Protocol.
"""

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .github_client import GitHubClient, Issue, get_user_repos
from .ai import (
    estimate_issue_size,
    breakdown_issue as ai_breakdown_issue,
    find_similar_issues as ai_find_similar,
    generate_closing_comment as ai_closing_comment,
    draft_issue_conversation,
    groom_issue_conversation,
    DraftIssue,
)

mcp = FastMCP("tshirts")


def _get_client(repo: str) -> GitHubClient:
    """Get GitHub client, validating token exists."""
    if not os.environ.get("GITHUB_TOKEN"):
        raise ValueError("GITHUB_TOKEN environment variable is required")
    return GitHubClient(repo)


# =============================================================================
# AI TOOLS - Wrap existing ai.py functions
# =============================================================================


@mcp.tool()
def estimate_issue(repo: str, issue_number: int) -> dict:
    """Estimate the t-shirt size (XS, S, M, L, XL) for a GitHub issue.

    Analyzes the issue's scope, complexity, risk, and unknowns to determine
    an appropriate size estimate.

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue number to estimate
    """
    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")
    size = estimate_issue_size(issue)
    return {
        "size": size,
        "issue_number": issue_number,
        "title": issue.title,
    }


@mcp.tool()
def breakdown_issue(repo: str, issue_number: int) -> list[dict]:
    """Break down a large issue into smaller actionable subtasks.

    Returns 3-7 subtasks that together complete the original issue.
    Each subtask includes a title, description, and size estimate.

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue number to break down
    """
    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")
    tasks = ai_breakdown_issue(issue)
    return [
        {"title": t.title, "description": t.description, "size": t.size}
        for t in tasks
    ]


@mcp.tool()
def draft_issue(description: str) -> list[dict]:
    """Generate well-structured issue draft(s) from a natural language description.

    Analyzes the description and creates one or more issue drafts with
    proper titles, descriptions, size estimates, and task breakdowns.

    Args:
        description: Natural language description of what to build or fix
    """
    # Use the conversation function with a single user message
    conversation = [{"role": "user", "content": description}]
    ready, question, drafts = draft_issue_conversation(conversation)

    if ready and drafts:
        return [
            {
                "title": d.title,
                "description": d.description,
                "size": d.size,
                "tasks": d.tasks,
            }
            for d in drafts
        ]
    else:
        # Not ready - return the question for follow-up
        return [{"needs_clarification": True, "question": question}]


@mcp.tool()
def refine_issue(repo: str, issue_number: int, context: str = "") -> dict:
    """Analyze an issue and suggest improvements to its description.

    Reviews the issue for clarity, completeness, and actionability.
    Returns suggestions and optionally a refined description.

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue to refine
        context: Additional context or answers to previous clarifying questions
    """
    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")

    # Build conversation from context if provided
    conversation = []
    if context:
        conversation.append({"role": "user", "content": context})

    ready, question, refined_description, suggestions = groom_issue_conversation(
        issue, conversation
    )

    result = {
        "issue_number": issue_number,
        "title": issue.title,
        "ready": ready,
        "suggestions": suggestions,
    }

    if ready and refined_description:
        result["refined_description"] = refined_description
    elif question:
        result["question"] = question

    return result


@mcp.tool()
def find_similar_issues(repo: str, title: str, description: str) -> list[dict]:
    """Find existing issues similar to a proposed new issue.

    Checks for duplicates, potential parent issues, or related issues
    before creating a new one.

    Args:
        repo: GitHub repository in owner/repo format
        title: Proposed issue title
        description: Proposed issue description
    """
    client = _get_client(repo)
    existing = client.get_open_issues()

    draft = DraftIssue(title=title, description=description, size="M", tasks=[])
    similar = ai_find_similar(draft, existing)

    return [
        {
            "issue_number": s.issue_number,
            "title": s.title,
            "relationship": s.relationship,
            "reasoning": s.reasoning,
        }
        for s in similar
    ]


@mcp.tool()
def generate_closing_comment(
    repo: str, issue_number: int, reason: Optional[str] = None
) -> dict:
    """Generate a suggested closing comment for an issue.

    Creates an appropriate closing message based on the issue content
    and any completed subtasks.

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue to generate comment for
        reason: Optional reason for closure (if no subtasks)
    """
    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")

    # Get sub-issues
    open_subs, closed_subs = client.get_sub_issues(issue_number)

    comment = ai_closing_comment(issue, closed_subs, reason)
    return {
        "issue_number": issue_number,
        "comment": comment,
        "open_subtasks": len(open_subs),
        "closed_subtasks": len(closed_subs),
    }


# =============================================================================
# ACTION TOOLS - GitHub operations
# =============================================================================


@mcp.tool()
def apply_size_label(repo: str, issue_number: int, size: str) -> dict:
    """Apply a t-shirt size label to a GitHub issue.

    Removes any existing size label and applies the new one.
    Valid sizes: XS, S, M, L, XL

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue number to label
        size: Size label (XS, S, M, L, or XL)
    """
    size = size.upper()
    if size not in ["XS", "S", "M", "L", "XL"]:
        raise ValueError(f"Invalid size: {size}. Must be XS, S, M, L, or XL")

    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")

    client.add_size_label(issue, size)
    return {
        "issue_number": issue_number,
        "label": f"size: {size}",
        "status": "applied",
    }


@mcp.tool()
def create_issue(
    repo: str,
    title: str,
    body: str,
    size: Optional[str] = None,
    labels: Optional[list[str]] = None,
) -> dict:
    """Create a new GitHub issue.

    Args:
        repo: GitHub repository in owner/repo format
        title: Issue title
        body: Issue description/body
        size: Optional t-shirt size (XS, S, M, L, XL) to auto-add label
        labels: Optional additional labels
    """
    client = _get_client(repo)

    all_labels = list(labels) if labels else []
    if size:
        size = size.upper()
        if size not in ["XS", "S", "M", "L", "XL"]:
            raise ValueError(f"Invalid size: {size}")
        all_labels.append(f"size: {size}")

    new_issue = client.create_issue(title=title, body=body, labels=all_labels)
    return {
        "issue_number": new_issue.number,
        "title": title,
        "url": f"https://github.com/{repo}/issues/{new_issue.number}",
    }


@mcp.tool()
def create_subtasks(repo: str, parent_issue: int, subtasks: list[dict]) -> dict:
    """Create multiple subtask issues linked to a parent issue.

    Each subtask should have 'title', 'description', and 'size' keys.
    All created issues will reference the parent in their body.

    Args:
        repo: GitHub repository in owner/repo format
        parent_issue: Parent issue number to link subtasks to
        subtasks: List of subtasks with 'title', 'description', 'size' keys
    """
    client = _get_client(repo)
    parent = client.get_issue(parent_issue)
    if not parent:
        raise ValueError(f"Parent issue #{parent_issue} not found in {repo}")

    created = []
    for task in subtasks:
        title = task.get("title", "Untitled")
        description = task.get("description", "")
        size = task.get("size", "M").upper()

        body = f"Parent issue: #{parent_issue}\n\n{description}"
        labels = [f"size: {size}"] if size in ["XS", "S", "M", "L", "XL"] else []

        new_issue = client.create_issue(title=title, body=body, labels=labels)
        created.append({"issue_number": new_issue.number, "title": title})

    # Add comment to parent linking subtasks
    if created:
        subtask_list = "\n".join(
            f"- #{c['issue_number']}: {c['title']}" for c in created
        )
        comment = f"## Subtasks created\n\n{subtask_list}"
        client.add_comment(parent, comment)

    return {
        "parent_issue": parent_issue,
        "subtasks_created": len(created),
        "subtasks": created,
    }


@mcp.tool()
def update_issue_body(repo: str, issue_number: int, body: str) -> dict:
    """Update the body/description of a GitHub issue.

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue to update
        body: New issue body/description
    """
    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")

    client.update_issue_body(issue, body)
    return {
        "issue_number": issue_number,
        "status": "updated",
    }


@mcp.tool()
def close_issue(
    repo: str, issue_number: int, comment: Optional[str] = None
) -> dict:
    """Close a GitHub issue with an optional closing comment.

    Args:
        repo: GitHub repository in owner/repo format
        issue_number: Issue to close
        comment: Optional closing comment
    """
    client = _get_client(repo)
    issue = client.get_issue(issue_number)
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {repo}")

    client.close_issue(issue, comment)
    return {
        "issue_number": issue_number,
        "status": "closed",
        "comment_added": comment is not None,
    }


# =============================================================================
# RESOURCES - Read-only data access
# =============================================================================


@mcp.resource("github://{repo}/issues")
def list_issues(repo: str) -> str:
    """List all open issues in a repository."""
    client = _get_client(repo)
    issues = client.get_open_issues()

    if not issues:
        return f"No open issues in {repo}"

    lines = [f"Open issues in {repo}:\n"]
    for issue in issues:
        labels = ", ".join(issue.labels) if issue.labels else "no labels"
        lines.append(f"#{issue.number}: {issue.title} [{labels}]")

    return "\n".join(lines)


@mcp.resource("github://{repo}/issues/{issue_number}")
def get_issue(repo: str, issue_number: int) -> str:
    """Get details of a specific issue."""
    client = _get_client(repo)
    issue = client.get_issue(int(issue_number))

    if not issue:
        return f"Issue #{issue_number} not found in {repo}"

    labels = ", ".join(issue.labels) if issue.labels else "none"
    return f"""Issue #{issue.number}: {issue.title}
Labels: {labels}

{issue.body or '(no description)'}"""


@mcp.resource("github://{repo}/issues/unestimated")
def list_unestimated_issues(repo: str) -> str:
    """List issues without size labels."""
    client = _get_client(repo)
    issues = client.get_issues_without_size_label()

    if not issues:
        return f"All issues in {repo} have size labels"

    lines = [f"Issues without size labels in {repo}:\n"]
    for issue in issues:
        lines.append(f"#{issue.number}: {issue.title}")

    return "\n".join(lines)


@mcp.resource("github://{repo}/issues/groomable")
def list_groomable_issues(repo: str) -> str:
    """List issues that may need refinement (size S or larger)."""
    client = _get_client(repo)
    issues = client.get_issues_for_grooming()

    if not issues:
        return f"No issues need grooming in {repo}"

    lines = [f"Issues that may need refinement in {repo}:\n"]
    for issue in issues:
        size = next(
            (l.replace("size: ", "") for l in issue.labels if l.startswith("size:")),
            "?",
        )
        lines.append(f"#{issue.number} [{size}]: {issue.title}")

    return "\n".join(lines)


@mcp.resource("github://repos")
def list_repos() -> str:
    """List GitHub repositories accessible to the authenticated user."""
    if not os.environ.get("GITHUB_TOKEN"):
        return "GITHUB_TOKEN environment variable is required"

    repos = get_user_repos()
    if not repos:
        return "No repositories found"

    return "Your repositories:\n" + "\n".join(repos[:50])


# =============================================================================
# ENTRY POINT
# =============================================================================


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
