"""CLI entry point for tshirts."""

import subprocess
import click
from rich.console import Console
from rich.prompt import Prompt, Confirm

from .github_client import GitHubClient, get_user_repos
from .ai import estimate_issue_size, breakdown_issue, draft_issue_conversation, groom_issue_conversation, find_similar_issues

console = Console()

def detect_repo_from_git() -> str | None:
    """Try to detect repo from current directory's git remote."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        # Parse GitHub URL: https://github.com/owner/repo.git or git@github.com:owner/repo.git
        if "github.com" in url:
            if url.startswith("git@"):
                # git@github.com:owner/repo.git
                path = url.split(":")[-1]
            else:
                # https://github.com/owner/repo.git
                path = url.split("github.com/")[-1]
            return path.removesuffix(".git")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None

def select_repo_interactive() -> str:
    """Let user select from their GitHub repos."""
    console.print("[dim]Fetching your repos...[/dim]")
    repos = get_user_repos()

    if not repos:
        console.print("[red]No repos found. Check your GITHUB_TOKEN.[/red]")
        raise SystemExit(1)

    console.print("\n[bold]Your repos:[/bold]")
    for i, repo in enumerate(repos[:20], 1):  # Show first 20
        console.print(f"  [cyan]{i:2}[/cyan]. {repo}")

    if len(repos) > 20:
        console.print(f"  [dim]... and {len(repos) - 20} more[/dim]")

    choice = Prompt.ask(
        "\nEnter number or repo name",
        default="1",
    )

    # Handle numeric selection
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(repos):
            return repos[idx]

    # Handle name input (partial match)
    for repo in repos:
        if choice in repo:
            return repo

    console.print(f"[red]Invalid selection: {choice}[/red]")
    raise SystemExit(1)

def resolve_repo(repo: str | None) -> str:
    """Resolve which repo to use."""
    if repo:
        return repo

    # Try to detect from git
    detected = detect_repo_from_git()
    if detected:
        console.print(f"[dim]Using repo from git: {detected}[/dim]")
        return detected

    # Interactive selection
    return select_repo_interactive()

@click.group()
@click.option("--repo", "-r", envvar="TSHIRTS_REPO", help="GitHub repo (owner/name)")
@click.pass_context
def main(ctx, repo):
    """tshirts - Break down GitHub issues into smaller pieces."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = repo

@main.command()
@click.pass_context
def estimate(ctx):
    """Assign size labels (XS, S, M, L, XL) to issues without them."""
    repo = resolve_repo(ctx.obj.get("repo"))

    client = GitHubClient(repo)
    issues = client.get_issues_without_size_label()

    if not issues:
        console.print("[green]All issues already have size labels![/green]")
        return

    console.print(f"Found [bold]{len(issues)}[/bold] issues without size labels")

    for issue in issues:
        console.print(f"\n[bold]#{issue.number}[/bold]: {issue.title}")
        size = estimate_issue_size(issue)
        console.print(f"  Estimated size: [cyan]{size}[/cyan]")
        client.add_size_label(issue, size)
        console.print(f"  [green]Label added![/green]")

@main.command()
@click.argument("issue_number", type=int)
@click.option("--create/--no-create", default=False, help="Create sub-issues automatically")
@click.pass_context
def breakdown(ctx, issue_number, create):
    """Break down an issue into smaller tasks."""
    repo = resolve_repo(ctx.obj.get("repo"))

    client = GitHubClient(repo)
    issue = client.get_issue(issue_number)

    if not issue:
        console.print(f"[red]Error:[/red] Issue #{issue_number} not found")
        raise SystemExit(1)

    console.print(f"\n[bold]Breaking down #{issue.number}:[/bold] {issue.title}\n")

    tasks = breakdown_issue(issue)

    for i, task in enumerate(tasks, 1):
        console.print(f"[cyan]{i}.[/cyan] [bold]{task.title}[/bold]")
        console.print(f"   Size: {task.size}")
        console.print(f"   {task.description[:100]}..." if len(task.description) > 100 else f"   {task.description}")
        console.print()

    # If --create flag passed, create immediately; otherwise prompt user
    should_create = create or Confirm.ask("\n[yellow]Create these issues?[/yellow]", default=False)

    if should_create:
        console.print("[yellow]Creating sub-issues...[/yellow]")
        for task in tasks:
            new_issue = client.create_issue(
                title=task.title,
                body=f"Parent issue: #{issue_number}\n\n{task.description}",
                labels=[f"size: {task.size}"],
            )
            console.print(f"  Created [green]#{new_issue.number}[/green]: {task.title}")

@main.command()
@click.pass_context
def new(ctx):
    """Create new issues with AI assistance."""
    repo = resolve_repo(ctx.obj.get("repo"))
    client = GitHubClient(repo)

    console.print("[bold]Let's create some issues![/bold]")
    console.print("[dim]I'll ask you some questions to help draft well-structured issues.[/dim]\n")

    # Start conversation
    conversation = []

    # Get initial description from user
    initial = Prompt.ask("[cyan]What would you like to build or fix?[/cyan]")
    conversation.append({"role": "user", "content": initial})

    # Conversation loop
    while True:
        console.print("\n[dim]Thinking...[/dim]")
        ready, question, drafts = draft_issue_conversation(conversation)

        if ready and drafts:
            # Show all draft issues
            console.print(f"\n[bold green]Here are your {len(drafts)} draft issue(s):[/bold green]")

            for i, draft in enumerate(drafts, 1):
                console.print(f"\n[bold cyan]Issue {i}:[/bold cyan]")
                console.print(f"[bold]Title:[/bold] {draft.title}")
                console.print(f"[bold]Size:[/bold] {draft.size}")
                console.print(f"\n[bold]Description:[/bold]\n{draft.description}")

                if draft.tasks:
                    console.print("\n[bold]Tasks:[/bold]")
                    for task in draft.tasks:
                        console.print(f"  - {task}")

            # Check for similar existing issues
            console.print()
            console.print("[dim]Checking for similar existing issues...[/dim]")
            existing_issues = client.get_open_issues()
            
            skip_issues = set()  # Track drafts to skip
            for idx, draft in enumerate(drafts):
                similar = find_similar_issues(draft, existing_issues)
                if similar:
                    console.print(f"\n[yellow]Potential matches for:[/yellow] {draft.title}")

                    for sim in similar:
                        rel_color = {"duplicate": "red", "subtask": "yellow", "related": "cyan"}.get(sim.relationship, "white")
                        console.print(f"  [{rel_color}]{sim.relationship.upper()}[/{rel_color}] #{sim.issue_number}: {sim.title}")
                        console.print(f"    [dim]{sim.reasoning}[/dim]")
                    
                    if any(s.relationship == "duplicate" for s in similar):
                        if not Confirm.ask(f"[red]Create anyway (possible duplicate)?[/red]", default=False):
                            skip_issues.add(idx)
                            console.print("[dim]Skipping this issue.[/dim]")
            
            # Filter out skipped drafts
            drafts = [d for i, d in enumerate(drafts) if i not in skip_issues]
            
            if not drafts:
                console.print("[dim]No issues to create.[/dim]")
                break
            
            # Confirm creation
            console.print()
            if Confirm.ask(f"[yellow]Create {len(drafts)} issue(s)?[/yellow]", default=True):
                for draft in drafts:
                    # Build issue body
                    body = draft.description
                    if draft.tasks:
                        body += "\n\n## Tasks\n"
                        for task in draft.tasks:
                            body += f"- [ ] {task}\n"

                    new_issue = client.create_issue(
                        title=draft.title,
                        body=body,
                        labels=[f"size: {draft.size}"],
                    )
                    console.print(f"[green]Created issue #{new_issue.number}:[/green] {draft.title}")
                    console.print(f"  [dim]https://github.com/{repo}/issues/{new_issue.number}[/dim]")
            else:
                console.print("[dim]Issues not created.[/dim]")
            break
        else:
            # Ask the follow-up question
            conversation.append({"role": "assistant", "content": question})
            console.print(f"\n[cyan]{question}[/cyan]")
            answer = Prompt.ask("")
            conversation.append({"role": "user", "content": answer})

@main.command()
@click.argument("issue_number", type=int, required=False)
@click.pass_context
def groom(ctx, issue_number):
    """Refine issues by gathering missing information (alias: refine)."""
    repo = resolve_repo(ctx.obj.get("repo"))
    client = GitHubClient(repo)

    # If no issue specified, show list of groomable issues
    if issue_number is None:
        issues = client.get_issues_for_grooming()
        if not issues:
            console.print("[green]No issues need grooming![/green]")
            return

        console.print(f"[bold]Issues that may need refinement ({len(issues)}):[/bold]")
        console.print()
        for issue in issues:
            size = next((l.replace('size: ', '') for l in issue.labels if l.startswith('size:')), '?')
            console.print(f"  [cyan]#{issue.number}[/cyan] [{size}] {issue.title}")

        console.print()
        console.print("[dim]Run 'tshirts groom <number>' to refine a specific issue.[/dim]")
        return

    # Get the specific issue
    issue = client.get_issue(issue_number)
    if not issue:
        console.print(f"[red]Error:[/red] Issue #{issue_number} not found")
        raise SystemExit(1)

    console.print(f"[bold]Grooming #{issue.number}:[/bold] {issue.title}")
    if len(issue.body) > 200:
        console.print("[dim]Current description:[/dim]")
        console.print(f"{issue.body[:200]}...")
    else:
        console.print("[dim]Current description:[/dim]")
        console.print(issue.body)
    console.print()

    # Start conversation
    conversation = []

    while True:
        console.print("[dim]Analyzing...[/dim]")
        ready, question, refined_description, suggestions = groom_issue_conversation(issue, conversation)

        # Show suggestions if any
        for suggestion in suggestions:
            console.print(f"[yellow]Suggestion:[/yellow] {suggestion}")

        if ready and refined_description:
            console.print()
            console.print("[bold green]Refined description:[/bold green]")
            console.print(refined_description)
            console.print()

            if Confirm.ask("[yellow]Update issue with this description?[/yellow]", default=True):
                client.update_issue_body(issue, refined_description)
                console.print(f"[green]Issue #{issue.number} updated![/green]")
            else:
                console.print("[dim]Issue not updated.[/dim]")
            break
        else:
            conversation.append({"role": "assistant", "content": question})
            console.print()
            console.print(f"[cyan]{question}[/cyan]")
            answer = Prompt.ask("")
            conversation.append({"role": "user", "content": answer})

@main.command()
@click.argument("issue_number", type=int, required=False)
@click.pass_context
def refine(ctx, issue_number):
    """Alias for groom - refine issues by gathering missing information."""
    ctx.invoke(groom, issue_number=issue_number)

if __name__ == "__main__":
    main()
