"""CLI entry point for tshirts."""

import click
from rich.console import Console

from .github_client import GitHubClient
from .ai import estimate_issue_size, breakdown_issue

console = Console()


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
    repo = ctx.obj.get("repo")
    if not repo:
        console.print("[red]Error:[/red] No repo specified. Use --repo or set TSHIRTS_REPO")
        raise SystemExit(1)

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
    repo = ctx.obj.get("repo")
    if not repo:
        console.print("[red]Error:[/red] No repo specified. Use --repo or set TSHIRTS_REPO")
        raise SystemExit(1)

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
