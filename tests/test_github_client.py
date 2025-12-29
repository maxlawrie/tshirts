"""Tests for the GitHub client module."""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from tshirts.github_client import (
    Issue,
    GitHubClient,
    get_user_repos,
    SIZE_LABELS,
)


class TestIssue:
    """Tests for the Issue dataclass."""

    def test_issue_creation(self):
        """Test creating an Issue directly."""
        issue = Issue(number=1, title="Test", body="Body", labels=["bug"])
        assert issue.number == 1
        assert issue.title == "Test"
        assert issue.body == "Body"
        assert issue.labels == ["bug"]

    def test_from_github(self):
        """Test creating Issue from GitHub issue object."""
        mock_gh_issue = MagicMock()
        mock_gh_issue.number = 42
        mock_gh_issue.title = "GitHub Issue"
        mock_gh_issue.body = "Description"
        mock_label = MagicMock()
        mock_label.name = "enhancement"
        mock_gh_issue.labels = [mock_label]

        issue = Issue.from_github(mock_gh_issue)

        assert issue.number == 42
        assert issue.title == "GitHub Issue"
        assert issue.body == "Description"
        assert issue.labels == ["enhancement"]

    def test_from_github_with_none_body(self):
        """Test that None body is converted to empty string."""
        mock_gh_issue = MagicMock()
        mock_gh_issue.number = 1
        mock_gh_issue.title = "Test"
        mock_gh_issue.body = None
        mock_gh_issue.labels = []

        issue = Issue.from_github(mock_gh_issue)

        assert issue.body == ""


class TestGetUserRepos:
    """Tests for get_user_repos function."""

    def test_requires_github_token(self):
        """Test that missing token raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                get_user_repos()

    def test_returns_repo_list(self):
        """Test successful repo listing."""
        mock_repo1 = MagicMock()
        mock_repo1.full_name = "user/repo1"
        mock_repo2 = MagicMock()
        mock_repo2.full_name = "user/repo2"

        mock_user = MagicMock()
        mock_user.get_repos.return_value = [mock_repo1, mock_repo2]

        mock_gh = MagicMock()
        mock_gh.get_user.return_value = mock_user

        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake-token"}):
            with patch("tshirts.github_client.Github", return_value=mock_gh):
                repos = get_user_repos()

        assert repos == ["user/repo1", "user/repo2"]
        mock_user.get_repos.assert_called_once_with(sort="updated")


class TestGitHubClientInit:
    """Tests for GitHubClient initialization."""

    def test_requires_github_token(self):
        """Test that missing token raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                GitHubClient("user/repo")

    def test_creates_missing_labels(self):
        """Test that missing size labels are created."""
        mock_label = MagicMock()
        mock_label.name = "size: M"  # Only M exists

        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = [mock_label]

        mock_gh = MagicMock()
        mock_gh.get_repo.return_value = mock_repo

        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake-token"}):
            with patch("tshirts.github_client.Github", return_value=mock_gh):
                GitHubClient("user/repo")

        # Should create 4 labels (XS, S, L, XL - not M since it exists)
        assert mock_repo.create_label.call_count == 4

    def test_handles_label_creation_error(self):
        """Test that label creation errors are ignored."""
        from github import GithubException

        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = []
        mock_repo.create_label.side_effect = GithubException(422, "exists", None)

        mock_gh = MagicMock()
        mock_gh.get_repo.return_value = mock_repo

        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake-token"}):
            with patch("tshirts.github_client.Github", return_value=mock_gh):
                # Should not raise
                client = GitHubClient("user/repo")

        assert client.repo == mock_repo


@pytest.fixture
def mock_github_client():
    """Fixture providing a GitHubClient with mocked GitHub API."""
    mock_repo = MagicMock()
    mock_repo.get_labels.return_value = []  # No existing labels

    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch.dict("os.environ", {"GITHUB_TOKEN": "fake-token"}):
        with patch("tshirts.github_client.Github", return_value=mock_gh):
            client = GitHubClient("user/repo")

    # Reset mock call counts after init
    mock_repo.reset_mock()

    return client, mock_repo


class TestGetIssue:
    """Tests for get_issue method."""

    def test_returns_issue(self, mock_github_client):
        """Test getting an issue by number."""
        client, mock_repo = mock_github_client

        mock_gh_issue = MagicMock()
        mock_gh_issue.number = 42
        mock_gh_issue.title = "Test Issue"
        mock_gh_issue.body = "Body"
        mock_gh_issue.labels = []
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = client.get_issue(42)

        assert issue is not None
        assert issue.number == 42
        assert issue.title == "Test Issue"
        mock_repo.get_issue.assert_called_once_with(42)

    def test_returns_none_on_not_found(self, mock_github_client):
        """Test that not found returns None."""
        from github import GithubException

        client, mock_repo = mock_github_client
        mock_repo.get_issue.side_effect = GithubException(404, "Not Found", None)

        issue = client.get_issue(999)

        assert issue is None


class TestGetIssuesWithoutSizeLabel:
    """Tests for get_issues_without_size_label method."""

    def test_filters_issues_without_size(self, mock_github_client):
        """Test filtering issues without size labels."""
        client, mock_repo = mock_github_client

        # Issue without size label
        mock_issue1 = MagicMock()
        mock_issue1.number = 1
        mock_issue1.title = "No size"
        mock_issue1.body = ""
        mock_issue1.labels = []
        mock_issue1.pull_request = None

        # Issue with size label
        mock_issue2 = MagicMock()
        mock_issue2.number = 2
        mock_issue2.title = "Has size"
        mock_issue2.body = ""
        mock_label = MagicMock()
        mock_label.name = "size: M"
        mock_issue2.labels = [mock_label]
        mock_issue2.pull_request = None

        mock_repo.get_issues.return_value = [mock_issue1, mock_issue2]

        issues = client.get_issues_without_size_label()

        assert len(issues) == 1
        assert issues[0].number == 1

    def test_skips_pull_requests(self, mock_github_client):
        """Test that pull requests are skipped."""
        client, mock_repo = mock_github_client

        mock_pr = MagicMock()
        mock_pr.number = 1
        mock_pr.pull_request = MagicMock()  # Has pull_request attribute

        mock_repo.get_issues.return_value = [mock_pr]

        issues = client.get_issues_without_size_label()

        assert len(issues) == 0


class TestGetOpenIssues:
    """Tests for get_open_issues method."""

    def test_returns_all_open_issues(self, mock_github_client):
        """Test getting all open issues."""
        client, mock_repo = mock_github_client

        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Open Issue"
        mock_issue.body = "Body"
        mock_issue.labels = []
        mock_issue.pull_request = None

        mock_repo.get_issues.return_value = [mock_issue]

        issues = client.get_open_issues()

        assert len(issues) == 1
        assert issues[0].title == "Open Issue"
        mock_repo.get_issues.assert_called_once_with(state="open")


class TestGetIssuesForGrooming:
    """Tests for get_issues_for_grooming method."""

    def test_returns_groomable_issues(self, mock_github_client):
        """Test getting issues with S+ size labels."""
        client, mock_repo = mock_github_client

        # XS issue - should NOT be included
        mock_xs = MagicMock()
        mock_xs.number = 1
        mock_xs.title = "XS Issue"
        mock_xs.body = ""
        xs_label = MagicMock()
        xs_label.name = "size: XS"
        mock_xs.labels = [xs_label]
        mock_xs.pull_request = None

        # M issue - should be included
        mock_m = MagicMock()
        mock_m.number = 2
        mock_m.title = "M Issue"
        mock_m.body = ""
        m_label = MagicMock()
        m_label.name = "size: M"
        mock_m.labels = [m_label]
        mock_m.pull_request = None

        mock_repo.get_issues.return_value = [mock_xs, mock_m]

        issues = client.get_issues_for_grooming()

        assert len(issues) == 1
        assert issues[0].number == 2


class TestAddSizeLabel:
    """Tests for add_size_label method."""

    def test_adds_size_label(self, mock_github_client):
        """Test adding a size label to an issue."""
        client, mock_repo = mock_github_client

        mock_gh_issue = MagicMock()
        mock_gh_issue.labels = []
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = Issue(number=1, title="Test", body="", labels=[])
        client.add_size_label(issue, "M")

        mock_gh_issue.add_to_labels.assert_called_once_with("size: M")

    def test_removes_existing_size_label(self, mock_github_client):
        """Test that existing size labels are removed first."""
        client, mock_repo = mock_github_client

        existing_label = MagicMock()
        existing_label.name = "size: S"

        mock_gh_issue = MagicMock()
        mock_gh_issue.labels = [existing_label]
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = Issue(number=1, title="Test", body="", labels=["size: S"])
        client.add_size_label(issue, "L")

        mock_gh_issue.remove_from_labels.assert_called_once_with(existing_label)
        mock_gh_issue.add_to_labels.assert_called_once_with("size: L")

    def test_rejects_invalid_size(self, mock_github_client):
        """Test that invalid sizes raise ValueError."""
        client, mock_repo = mock_github_client

        issue = Issue(number=1, title="Test", body="", labels=[])

        with pytest.raises(ValueError, match="Invalid size"):
            client.add_size_label(issue, "XXL")


class TestCreateIssue:
    """Tests for create_issue method."""

    def test_creates_issue(self, mock_github_client):
        """Test creating a new issue."""
        client, mock_repo = mock_github_client

        client.create_issue("New Issue", "Description", ["bug"])

        mock_repo.create_issue.assert_called_once_with(
            title="New Issue",
            body="Description",
            labels=["bug"]
        )

    def test_creates_issue_without_labels(self, mock_github_client):
        """Test creating issue with no labels."""
        client, mock_repo = mock_github_client

        client.create_issue("New Issue", "Description")

        mock_repo.create_issue.assert_called_once_with(
            title="New Issue",
            body="Description",
            labels=[]
        )


class TestUpdateIssueBody:
    """Tests for update_issue_body method."""

    def test_updates_body(self, mock_github_client):
        """Test updating an issue's body."""
        client, mock_repo = mock_github_client

        mock_gh_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = Issue(number=1, title="Test", body="Old", labels=[])
        client.update_issue_body(issue, "New body")

        mock_gh_issue.edit.assert_called_once_with(body="New body")


class TestAddComment:
    """Tests for add_comment method."""

    def test_adds_comment(self, mock_github_client):
        """Test adding a comment to an issue."""
        client, mock_repo = mock_github_client

        mock_gh_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = Issue(number=1, title="Test", body="", labels=[])
        client.add_comment(issue, "This is a comment")

        mock_gh_issue.create_comment.assert_called_once_with("This is a comment")


class TestGetSubIssues:
    """Tests for get_sub_issues method."""

    def test_finds_sub_issues(self, mock_github_client):
        """Test finding sub-issues by parent reference."""
        client, mock_repo = mock_github_client

        # Open sub-issue
        mock_open = MagicMock()
        mock_open.number = 2
        mock_open.title = "Sub 1"
        mock_open.body = "Parent issue: #1\nDescription"
        mock_open.labels = []
        mock_open.pull_request = None
        mock_open.state = "open"

        # Closed sub-issue
        mock_closed = MagicMock()
        mock_closed.number = 3
        mock_closed.title = "Sub 2"
        mock_closed.body = "Parent issue: #1\nDone"
        mock_closed.labels = []
        mock_closed.pull_request = None
        mock_closed.state = "closed"

        # Unrelated issue
        mock_other = MagicMock()
        mock_other.number = 4
        mock_other.title = "Other"
        mock_other.body = "Not a sub-issue"
        mock_other.labels = []
        mock_other.pull_request = None
        mock_other.state = "open"

        mock_repo.get_issues.return_value = [mock_open, mock_closed, mock_other]

        open_issues, closed_issues = client.get_sub_issues(1)

        assert len(open_issues) == 1
        assert open_issues[0].number == 2
        assert len(closed_issues) == 1
        assert closed_issues[0].number == 3

    def test_handles_none_body(self, mock_github_client):
        """Test handling issues with None body."""
        client, mock_repo = mock_github_client

        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.body = None
        mock_issue.pull_request = None

        mock_repo.get_issues.return_value = [mock_issue]

        open_issues, closed_issues = client.get_sub_issues(1)

        assert len(open_issues) == 0
        assert len(closed_issues) == 0


class TestCloseIssue:
    """Tests for close_issue method."""

    def test_closes_issue(self, mock_github_client):
        """Test closing an issue."""
        client, mock_repo = mock_github_client

        mock_gh_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = Issue(number=1, title="Test", body="", labels=[])
        client.close_issue(issue)

        mock_gh_issue.edit.assert_called_once_with(state="closed")
        mock_gh_issue.create_comment.assert_not_called()

    def test_closes_with_comment(self, mock_github_client):
        """Test closing an issue with a comment."""
        client, mock_repo = mock_github_client

        mock_gh_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_gh_issue

        issue = Issue(number=1, title="Test", body="", labels=[])
        client.close_issue(issue, "Closing comment")

        mock_gh_issue.create_comment.assert_called_once_with("Closing comment")
        mock_gh_issue.edit.assert_called_once_with(state="closed")
