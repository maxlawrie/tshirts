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


@dataclass
class DraftIssue:
    """A draft issue ready to be created."""
    title: str
    description: str
    size: str
    tasks: list[str]


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

CONVERSATION_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "ready": {"type": "boolean"},
        "question": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "size": {"type": "string", "enum": ["XS", "S", "M", "L", "XL"]},
                    "tasks": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    },
    "required": ["ready"]
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
    prompt = f"""You are an experienced software engineer estimating the complexity of a GitHub issue.

ISSUE TO ESTIMATE:
Title: {issue.title}
Number: #{issue.number}

Description:
{issue.body}

ESTIMATION CRITERIA:

Consider these factors when estimating:
1. SCOPE: How many files/components need changes?
2. COMPLEXITY: Is this straightforward or does it require deep thinking?
3. RISK: Could this break existing functionality? Need careful testing?
4. DEPENDENCIES: Are there external dependencies or coordination needed?
5. UNKNOWNS: Is the solution clear or does it need investigation?

SIZE DEFINITIONS:

XS (Extra Small) - Under 30 minutes
- Single-line or few-line changes
- Typo fixes, copy changes, config tweaks
- No logic changes, no testing needed
- Examples: Fix spelling in README, update a constant, add a comment

S (Small) - 1-2 hours
- Contained to 1-2 files
- Clear solution, minimal complexity
- Simple bug fix with obvious cause
- Examples: Fix null check, add validation, simple UI tweak

M (Medium) - Half day to 1 day
- Changes across 3-5 files
- Some complexity, may need design decisions
- Requires testing but scope is clear
- Examples: Add new API endpoint, implement a form, refactor a function

L (Large) - 2-3 days
- Significant feature or refactoring
- Multiple components affected
- Requires careful planning and testing
- May need code review discussions
- Examples: New feature with UI+API+DB, significant refactor, complex bug

XL (Extra Large) - 1+ week
- Major feature or architectural change
- High complexity or many unknowns
- Should probably be broken into smaller issues
- Cross-team coordination may be needed
- Examples: New authentication system, major migration, new module

ESTIMATION GUIDELINES:
- When uncertain, size UP (it is better to overestimate)
- Vague or unclear issues should be sized larger (unknowns add time)
- Consider testing time, not just coding time
- If description is minimal, assume medium complexity

Based on the above criteria, estimate this issue's size."""

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
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
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
                title=task.get("title") or "Untitled",
                description=task.get("description") or "",
                size=(task.get("size") or "M").upper(),
            )
            for task in tasks
        ]
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return [
            SubTask(
                title=f"Implement: {issue.title}",
                description=issue.body,
                size="M",
            )
        ]


def draft_issue_conversation(conversation: list[dict]) -> tuple[bool, str | None, list[DraftIssue] | None]:
    """Continue a conversation to draft new issues.

    Returns:
        (ready, question, issues) where:
        - ready: True if the issues are ready to create
        - question: Next question to ask (if not ready)
        - issues: List of draft issues (if ready)
    """
    history = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in conversation
    )

    prompt = f"""You are helping draft GitHub issues. Have a conversation to understand what the user wants to build.

Ask clarifying questions to understand:
- What problem this solves or what feature it adds
- Key requirements or acceptance criteria
- Any technical constraints or preferences

IMPORTANT: If the user describes multiple distinct features or capabilities, create SEPARATE issues for each one.
Each issue should be independently implementable. Never combine unrelated features into a single issue.

Conversation so far:
{history}

If you need more information, set ready=false and ask ONE focused question.
If you have enough information, set ready=true and provide the issues array (one issue per distinct feature)."""

    try:
        response = _call_claude(prompt, CONVERSATION_SCHEMA)
        data = json.loads(response)

        if "structured_output" in data:
            data = data["structured_output"]

        ready = data.get("ready", False)

        if ready and "issues" in data:
            issues = []
            for issue_data in data["issues"]:
                issues.append(DraftIssue(
                    title=issue_data.get("title", "Untitled"),
                    description=issue_data.get("description", ""),
                    size=issue_data.get("size", "M"),
                    tasks=issue_data.get("tasks", []),
                ))
            return True, None, issues if issues else None
        else:
            return False, data.get("question", "Can you tell me more?"), None

    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return False, "Can you describe what you want to build?", None

GROOM_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "ready": {"type": "boolean"},
        "question": {"type": "string"},
        "refined_description": {"type": "string"},
        "suggestions": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["ready"]
})


def groom_issue_conversation(issue: Issue, conversation: list[dict]) -> tuple[bool, str | None, str | None, list[str]]:
    """Continue a conversation to refine an existing issue.

    Returns:
        (ready, question, refined_description, suggestions) where:
        - ready: True if the issue is fully refined
        - question: Next clarifying question (if not ready)
        - refined_description: Updated issue body (if ready)
        - suggestions: List of suggestions (e.g., "consider breaking down")
    """
    history = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in conversation
    )

    prompt = f"""You are helping refine a GitHub issue to make it clearer and more actionable.

Issue #{issue.number}: {issue.title}
Current size: {next((l.replace('size: ', '') for l in issue.labels if l.startswith('size:')), 'Unknown')}

Current description:
{issue.body}

Analyze this issue and identify what needs clarification:
- Unclear requirements or acceptance criteria
- Ambiguous technical approach
- Missing context or constraints
- Scope too large (may need breakdown into smaller issues)

Conversation so far:
{history}

If the issue needs clarification, set ready=false and ask ONE focused question.
If the issue is well-defined or you have gathered enough information, set ready=true and provide:
- refined_description: The improved issue description incorporating any new information
- suggestions: Any recommendations (e.g., "Consider breaking this into smaller issues")"""

    try:
        response = _call_claude(prompt, GROOM_SCHEMA)
        data = json.loads(response)

        if "structured_output" in data:
            data = data["structured_output"]

        ready = data.get("ready", False)
        suggestions = data.get("suggestions", [])

        if ready:
            return True, None, data.get("refined_description", issue.body), suggestions
        else:
            return False, data.get("question", "Can you clarify this issue?"), None, suggestions

    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return False, "Can you tell me more about this issue?", None, []

SIMILAR_ISSUES_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "similar_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_number": {"type": "integer"},
                    "relationship": {"type": "string", "enum": ["duplicate", "subtask", "related", "distinct"]},
                    "reasoning": {"type": "string"}
                },
                "required": ["issue_number", "relationship", "reasoning"]
            }
        }
    },
    "required": ["similar_issues"]
})


@dataclass
class SimilarIssue:
    """A potentially similar existing issue."""
    issue_number: int
    title: str
    relationship: str  # duplicate, subtask, related, distinct
    reasoning: str


def find_similar_issues(draft: DraftIssue, existing_issues: list) -> list[SimilarIssue]:
    """Find existing issues that are similar to the draft.
    
    Returns issues that are duplicates, potential parents (for subtasks), or related.
    """
    if not existing_issues:
        return []
    
    
    issues_text = "\n".join(
        f"#{i.number}: {i.title}\n  {i.body[:200] if i.body else '(no description)'}"
        for i in existing_issues[:50]  # Limit to 50 issues
    )
    
    prompt = f"""Compare this new issue draft against existing issues to find duplicates or related issues.

NEW ISSUE DRAFT:
Title: {draft.title}
Description: {draft.description}

EXISTING ISSUES:
{issues_text}

For each existing issue that is similar, determine:
- "duplicate": Same problem/feature, should not create new issue
- "subtask": New issue could be a subtask of the existing one
- "related": Related but distinct, worth linking
- "distinct": Not related

Only include issues that are duplicate, subtask, or related. Omit distinct issues.
Provide clear reasoning for each match."""

    try:
        response = _call_claude(prompt, SIMILAR_ISSUES_SCHEMA)
        data = json.loads(response)
        
        if "structured_output" in data:
            data = data["structured_output"]
        
        similar = []
        issue_map = {i.number: i for i in existing_issues}
        
        for item in data.get("similar_issues", []):
            num = item.get("issue_number")
            if num in issue_map and item.get("relationship") != "distinct":
                similar.append(SimilarIssue(
                    issue_number=num,
                    title=issue_map[num].title,
                    relationship=item.get("relationship", "related"),
                    reasoning=item.get("reasoning", "")
                ))
        
        return similar
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return []


CLOSING_COMMENT_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "comment": {"type": "string"}
    },
    "required": ["comment"]
})


def generate_closing_comment(issue, sub_issues: list, reason: str | None = None) -> str:
    """Generate a closing comment for an issue.
    
    Args:
        issue: The issue being closed
        sub_issues: List of completed sub-issues (if any)
        reason: Optional reason for closure (if no sub-issues)
    
    Returns:
        A suggested closing comment
    """
    sub_issues_text = ""
    if sub_issues:
        sub_issues_text = "Completed sub-issues:\n" + "\n".join(
            f"- #{i.number}: {i.title}" for i in sub_issues
        )
    
    reason_text = f"\nClosure reason provided: {reason}" if reason else ""
    
    prompt = f"""Generate a brief, professional closing comment for this GitHub issue.

Issue #{issue.number}: {issue.title}

Description:
{issue.body[:500] if issue.body else '(no description)'}

{sub_issues_text}
{reason_text}

Write a 1-3 sentence closing comment that:
- Summarizes what was accomplished
- Thanks contributors if applicable
- Is concise and professional"""

    try:
        response = _call_claude(prompt, CLOSING_COMMENT_SCHEMA)
        data = json.loads(response)
        
        if "structured_output" in data:
            data = data["structured_output"]
        
        return data.get("comment", "Issue closed.")
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError, TypeError, AttributeError, subprocess.TimeoutExpired):
        if sub_issues:
            return f"Completed with {len(sub_issues)} sub-task(s). Closing."
        return "Issue closed."
