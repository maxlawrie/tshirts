"""CLI entry point for tshirts."""

import subprocess
import click
from rich.console import Console
from rich.prompt import Prompt

from .github_client import GitHubClient, get_user_repos
from .ai import estimate_issue_size, breakdown_issue

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

    if create:
        console.print("[yellow]Creating sub-issues...[/yellow]")
        for task in tasks:
            new_issue = client.create_issue(
                title=task.title,
                body=f"Parent issue: #{issue_number}\n\n{task.description}",
                labels=[f"size: {task.size}"],
            )
            console.print(f"  Created [green]#{new_issue.number}[/green]: {task.title}")


if __name__ == "__main__":
    main()
