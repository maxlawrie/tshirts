"""GitHub API client for tshirts."""

import os
from dataclasses import dataclass
from github import Github, GithubException


SIZE_LABELS = ["size: XS", "size: S", "size: M", "size: L", "size: XL"]


@dataclass
class Issue:
    """Represents a GitHub issue."""
    number: int
    title: str
    body: str
    labels: list[str]

    @classmethod
    def from_github(cls, gh_issue) -> "Issue":
        return cls(
            number=gh_issue.number,
            title=gh_issue.title,
            body=gh_issue.body or "",
            labels=[label.name for label in gh_issue.labels],
        )


class GitHubClient:
    """Client for interacting with GitHub issues."""

    def __init__(self, repo_name: str):
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable required")

        self.gh = Github(token)
        self.repo = self.gh.get_repo(repo_name)
        self._ensure_size_labels_exist()

    def _ensure_size_labels_exist(self):
        """Create size labels if they don't exist."""
        existing = {label.name for label in self.repo.get_labels()}
        colors = {
            "size: XS": "0e8a16",  # green
            "size: S": "7bc96f",   # light green
            "size: M": "fef2c0",   # yellow
            "size: L": "f9a03f",   # orange
            "size: XL": "d93f0b",  # red
        }
        for label in SIZE_LABELS:
            if label not in existing:
                try:
                    self.repo.create_label(label, colors[label])
                except GithubException:
                    pass  # Label might already exist

    def get_issues_without_size_label(self) -> list[Issue]:
        """Get all open issues that don't have a size label."""
        issues = []
        for gh_issue in self.repo.get_issues(state="open"):
            if gh_issue.pull_request:
                continue  # Skip pull requests
            issue = Issue.from_github(gh_issue)
            if not any(label in SIZE_LABELS for label in issue.labels):
                issues.append(issue)
        return issues

    def get_issue(self, number: int) -> Issue | None:
        """Get a specific issue by number."""
        try:
            gh_issue = self.repo.get_issue(number)
            return Issue.from_github(gh_issue)
        except GithubException:
            return None

    def add_size_label(self, issue: Issue, size: str):
        """Add a size label to an issue."""
        label = f"size: {size}"
        if label not in SIZE_LABELS:
            raise ValueError(f"Invalid size: {size}")

        gh_issue = self.repo.get_issue(issue.number)

        # Remove any existing size labels
        for existing_label in gh_issue.labels:
            if existing_label.name in SIZE_LABELS:
                gh_issue.remove_from_labels(existing_label)

        gh_issue.add_to_labels(label)

    def create_issue(self, title: str, body: str, labels: list[str] | None = None):
        """Create a new issue."""
        return self.repo.create_issue(title=title, body=body, labels=labels or [])
