"""Tests for the MCP server."""

import pytest
from unittest.mock import patch, MagicMock

from tshirts.mcp import (
    mcp,
    estimate_issue,
    breakdown_issue,
    apply_size_label,
    create_issue,
    draft_issue,
    find_similar_issues,
)
from tshirts.github_client import Issue


@pytest.fixture
def mock_github_client():
    """Mock the GitHubClient."""
    with patch("tshirts.mcp.GitHubClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_github_token():
    """Mock GITHUB_TOKEN environment variable."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
        yield


class TestMCPServerSetup:
    """Tests for MCP server configuration."""

    def test_server_has_correct_name(self):
        """Test that the MCP server has the correct name."""
        assert mcp.name == "tshirts"

    def test_all_tools_registered(self):
        """Test that all expected tools are registered."""
        expected_tools = [
            "estimate_issue",
            "breakdown_issue",
            "draft_issue",
            "refine_issue",
            "find_similar_issues",
            "generate_closing_comment",
            "apply_size_label",
            "create_issue",
            "create_subtasks",
            "update_issue_body",
            "close_issue",
        ]
        registered = set(mcp._tool_manager._tools.keys())
        for tool in expected_tools:
            assert tool in registered, f"Tool {tool} not registered"


class TestEstimateIssueTool:
    """Tests for the estimate_issue tool."""

    def test_estimate_issue_success(self, mock_github_client, mock_github_token):
        """Test successful issue estimation."""
        issue = Issue(number=1, title="Test Issue", body="Description", labels=[])
        mock_github_client.get_issue.return_value = issue

        with patch("tshirts.mcp.estimate_issue_size", return_value="M"):
            result = estimate_issue("owner/repo", 1)

        assert result["size"] == "M"
        assert result["issue_number"] == 1
        assert result["title"] == "Test Issue"

    def test_estimate_issue_not_found(self, mock_github_client, mock_github_token):
        """Test estimation when issue not found."""
        mock_github_client.get_issue.return_value = None

        with pytest.raises(ValueError, match="not found"):
            estimate_issue("owner/repo", 999)

    def test_estimate_issue_no_token(self):
        """Test that missing token raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                estimate_issue("owner/repo", 1)


class TestBreakdownIssueTool:
    """Tests for the breakdown_issue tool."""

    def test_breakdown_issue_success(self, mock_github_client, mock_github_token):
        """Test successful issue breakdown."""
        issue = Issue(number=1, title="Big Feature", body="Do stuff", labels=[])
        mock_github_client.get_issue.return_value = issue

        from tshirts.ai import SubTask
        mock_tasks = [
            SubTask(title="Task 1", description="Do thing 1", size="S"),
            SubTask(title="Task 2", description="Do thing 2", size="M"),
        ]

        with patch("tshirts.mcp.ai_breakdown_issue", return_value=mock_tasks):
            result = breakdown_issue("owner/repo", 1)

        assert len(result) == 2
        assert result[0]["title"] == "Task 1"
        assert result[0]["size"] == "S"


class TestApplySizeLabelTool:
    """Tests for the apply_size_label tool."""

    def test_apply_size_label_success(self, mock_github_client, mock_github_token):
        """Test successful label application."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        mock_github_client.get_issue.return_value = issue

        result = apply_size_label("owner/repo", 1, "M")

        assert result["label"] == "size: M"
        assert result["status"] == "applied"
        mock_github_client.add_size_label.assert_called_once()

    def test_apply_size_label_invalid_size(self, mock_github_client, mock_github_token):
        """Test that invalid size raises error."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        mock_github_client.get_issue.return_value = issue

        with pytest.raises(ValueError, match="Invalid size"):
            apply_size_label("owner/repo", 1, "XXL")

    def test_apply_size_label_case_insensitive(self, mock_github_client, mock_github_token):
        """Test that size is case-insensitive."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        mock_github_client.get_issue.return_value = issue

        result = apply_size_label("owner/repo", 1, "xs")

        assert result["label"] == "size: XS"


class TestCreateIssueTool:
    """Tests for the create_issue tool."""

    def test_create_issue_success(self, mock_github_client, mock_github_token):
        """Test successful issue creation."""
        mock_new_issue = MagicMock()
        mock_new_issue.number = 42
        mock_github_client.create_issue.return_value = mock_new_issue

        result = create_issue("owner/repo", "New Feature", "Description", size="M")

        assert result["issue_number"] == 42
        assert "url" in result
        mock_github_client.create_issue.assert_called_once()

    def test_create_issue_with_labels(self, mock_github_client, mock_github_token):
        """Test issue creation with custom labels."""
        mock_new_issue = MagicMock()
        mock_new_issue.number = 43
        mock_github_client.create_issue.return_value = mock_new_issue

        result = create_issue(
            "owner/repo", "Bug", "Fix it", labels=["bug", "priority:high"]
        )

        call_args = mock_github_client.create_issue.call_args
        assert "bug" in call_args.kwargs["labels"]


class TestDraftIssueTool:
    """Tests for the draft_issue tool."""

    def test_draft_issue_ready(self, mock_github_token):
        """Test drafting when AI returns ready result."""
        from tshirts.ai import DraftIssue
        mock_drafts = [
            DraftIssue(
                title="New Feature",
                description="Implement feature",
                size="M",
                tasks=["Task 1", "Task 2"],
            )
        ]

        with patch("tshirts.mcp.draft_issue_conversation", return_value=(True, None, mock_drafts)):
            result = draft_issue("Build a new feature")

        assert len(result) == 1
        assert result[0]["title"] == "New Feature"
        assert "tasks" in result[0]

    def test_draft_issue_needs_clarification(self, mock_github_token):
        """Test drafting when AI needs more info."""
        with patch("tshirts.mcp.draft_issue_conversation", return_value=(False, "What framework?", None)):
            result = draft_issue("Build something")

        assert result[0]["needs_clarification"] is True
        assert "question" in result[0]


class TestFindSimilarIssuesTool:
    """Tests for the find_similar_issues tool."""

    def test_find_similar_issues_with_matches(self, mock_github_client, mock_github_token):
        """Test finding similar issues."""
        mock_github_client.get_open_issues.return_value = [
            Issue(number=1, title="Existing", body="stuff", labels=[])
        ]

        from tshirts.ai import SimilarIssue
        mock_similar = [
            SimilarIssue(
                issue_number=1,
                title="Existing",
                relationship="related",
                reasoning="Similar scope"
            )
        ]

        with patch("tshirts.mcp.ai_find_similar", return_value=mock_similar):
            result = find_similar_issues("owner/repo", "New Feature", "Do stuff")

        assert len(result) == 1
        assert result[0]["issue_number"] == 1
        assert result[0]["relationship"] == "related"

    def test_find_similar_issues_no_matches(self, mock_github_client, mock_github_token):
        """Test when no similar issues found."""
        mock_github_client.get_open_issues.return_value = []

        with patch("tshirts.mcp.ai_find_similar", return_value=[]):
            result = find_similar_issues("owner/repo", "Unique Feature", "Unique")

        assert result == []
