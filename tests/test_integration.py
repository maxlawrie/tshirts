"""Integration tests for end-to-end workflows.

These tests verify complete user workflows with all components working together.
External dependencies (GitHub API, Claude CLI) are mocked at the boundary.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call
from click.testing import CliRunner

from tshirts.cli import main
from tshirts.github_client import Issue
from tshirts.ai import SubTask, DraftIssue


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_github():
    """Mock the GitHub client at the module level."""
    with patch("tshirts.cli.GitHubClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_claude():
    """Mock the Claude CLI subprocess calls."""
    with patch("tshirts.ai.subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def mock_resolve_repo():
    """Mock repo resolution to return a test repo."""
    with patch("tshirts.cli.resolve_repo", return_value="test/repo"):
        yield


def make_claude_response(data: dict) -> MagicMock:
    """Create a mock Claude CLI response."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps({"structured_output": data})
    result.stderr = ""
    return result


class TestEstimateWorkflow:
    """Integration tests for the full estimate workflow."""

    def test_estimate_single_issue_accept(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test estimating a single issue and accepting the suggestion."""
        # Setup: one issue without size label
        issue = Issue(number=1, title="Add login page", body="Create a login form", labels=[])
        mock_github.get_issues_without_size_label.return_value = [issue]

        # Claude returns size estimate
        mock_claude.return_value = make_claude_response({"size": "M"})

        # Run estimate with accept input
        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate"], input="a\n")

        assert result.exit_code == 0
        assert "Suggested: M" in result.output
        assert "Labeled M" in result.output
        assert "1 labeled, 0 skipped" in result.output
        mock_github.add_size_label.assert_called_once_with(issue, "M")

    def test_estimate_single_issue_change(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test estimating and changing the suggested size."""
        issue = Issue(number=1, title="Big refactor", body="Major changes", labels=[])
        mock_github.get_issues_without_size_label.return_value = [issue]
        mock_claude.return_value = make_claude_response({"size": "M"})

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate"], input="c\nL\n")

        assert result.exit_code == 0
        assert "Labeled L" in result.output
        mock_github.add_size_label.assert_called_once_with(issue, "L")

    def test_estimate_single_issue_skip(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test skipping an issue during estimation."""
        issue = Issue(number=1, title="Unclear task", body="", labels=[])
        mock_github.get_issues_without_size_label.return_value = [issue]
        mock_claude.return_value = make_claude_response({"size": "S"})

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate"], input="s\n")

        assert result.exit_code == 0
        assert "Skipped" in result.output
        assert "0 labeled, 1 skipped" in result.output
        mock_github.add_size_label.assert_not_called()

    def test_estimate_multiple_issues_yes_flag(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test batch estimation with --yes flag."""
        issues = [
            Issue(number=1, title="Task 1", body="Do thing 1", labels=[]),
            Issue(number=2, title="Task 2", body="Do thing 2", labels=[]),
            Issue(number=3, title="Task 3", body="Do thing 3", labels=[]),
        ]
        mock_github.get_issues_without_size_label.return_value = issues

        # Return different sizes for each
        mock_claude.side_effect = [
            make_claude_response({"size": "XS"}),
            make_claude_response({"size": "S"}),
            make_claude_response({"size": "M"}),
        ]

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate", "--yes"])

        assert result.exit_code == 0
        assert "3 labeled, 0 skipped" in result.output
        assert mock_github.add_size_label.call_count == 3

    def test_estimate_no_issues(self, cli_runner, mock_github, mock_resolve_repo):
        """Test when all issues already have labels."""
        mock_github.get_issues_without_size_label.return_value = []

        result = cli_runner.invoke(main, ["estimate"])

        assert result.exit_code == 0
        assert "already have size labels" in result.output

    def test_estimate_claude_error_fallback(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test that estimation falls back to M on Claude error."""
        issue = Issue(number=1, title="Test", body="Test body", labels=[])
        mock_github.get_issues_without_size_label.return_value = [issue]

        # Claude returns error
        error_result = MagicMock()
        error_result.returncode = 1
        error_result.stdout = ""
        error_result.stderr = "Error"
        mock_claude.return_value = error_result

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate", "--yes"])

        assert result.exit_code == 0
        # Should fall back to M
        mock_github.add_size_label.assert_called_once_with(issue, "M")


class TestBreakdownWorkflow:
    """Integration tests for the full breakdown workflow."""

    def test_breakdown_with_create_flag(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test breaking down an issue and creating sub-issues."""
        parent = Issue(number=10, title="Big Feature", body="Implement big feature", labels=["size: XL"])
        mock_github.get_issue.return_value = parent

        # Claude returns breakdown
        mock_claude.return_value = make_claude_response({
            "tasks": [
                {"title": "Setup infrastructure", "description": "Create base setup", "size": "S"},
                {"title": "Implement core logic", "description": "Main implementation", "size": "M"},
                {"title": "Add tests", "description": "Write unit tests", "size": "S"},
            ]
        })

        # Mock created issues
        created_issues = []
        for i in range(3):
            mock_issue = MagicMock()
            mock_issue.number = 11 + i
            created_issues.append(mock_issue)
        mock_github.create_issue.side_effect = created_issues

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["breakdown", "10", "--create"])

        assert result.exit_code == 0
        assert "Created #11" in result.output
        assert "Created #12" in result.output
        assert "Created #13" in result.output
        assert mock_github.create_issue.call_count == 3
        mock_github.add_comment.assert_called_once()

    def test_breakdown_interactive_create_selected(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test interactive breakdown - select and create some tasks."""
        parent = Issue(number=5, title="Feature", body="Do feature", labels=[])
        mock_github.get_issue.return_value = parent

        mock_claude.return_value = make_claude_response({
            "tasks": [
                {"title": "Task A", "description": "Do A", "size": "S"},
                {"title": "Task B", "description": "Do B", "size": "M"},
            ]
        })

        mock_issue = MagicMock()
        mock_issue.number = 100
        mock_github.create_issue.return_value = mock_issue

        with patch("tshirts.ai._find_claude", return_value="claude"):
            # Enter edit mode, deselect task 2, then done, then create
            result = cli_runner.invoke(main, ["breakdown", "5"], input="e\n2\nt\nd\nc\n")

        assert result.exit_code == 0
        # Only one issue should be created (task 1)
        assert mock_github.create_issue.call_count == 1

    def test_breakdown_issue_not_found(
        self, cli_runner, mock_github, mock_resolve_repo
    ):
        """Test breakdown when issue doesn't exist."""
        mock_github.get_issue.return_value = None

        result = cli_runner.invoke(main, ["breakdown", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_breakdown_claude_error_fallback(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test breakdown falls back to single task on Claude error."""
        parent = Issue(number=1, title="Do Thing", body="Description", labels=[])
        mock_github.get_issue.return_value = parent

        # Claude returns invalid JSON
        error_result = MagicMock()
        error_result.returncode = 0
        error_result.stdout = "not json"
        error_result.stderr = ""
        mock_claude.return_value = error_result

        mock_issue = MagicMock()
        mock_issue.number = 2
        mock_github.create_issue.return_value = mock_issue

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["breakdown", "1", "--create"])

        assert result.exit_code == 0
        # Fallback creates single task with original issue title
        assert mock_github.create_issue.call_count == 1


class TestNewIssueWorkflow:
    """Integration tests for the new issue creation workflow."""

    def test_new_issue_single_turn(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test creating a new issue when Claude is ready immediately."""
        # First call: Claude says ready with issue
        mock_claude.return_value = make_claude_response({
            "ready": True,
            "issues": [{
                "title": "Add dark mode",
                "description": "Implement dark mode toggle",
                "size": "M",
                "tasks": ["Add toggle", "Update styles"]
            }]
        })

        mock_github.get_open_issues.return_value = []  # No similar issues

        mock_created = MagicMock()
        mock_created.number = 50
        mock_github.create_issue.return_value = mock_created

        with patch("tshirts.ai._find_claude", return_value="claude"):
            # Initial input, then confirm creation
            result = cli_runner.invoke(main, ["new"], input="Add dark mode\ny\n")

        assert result.exit_code == 0
        assert "Created issue #50" in result.output

    def test_new_issue_multi_turn_conversation(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test multi-turn conversation for issue creation."""
        # First call: ask question
        # Second call: ready with issue
        mock_claude.side_effect = [
            make_claude_response({
                "ready": False,
                "question": "What framework are you using?"
            }),
            make_claude_response({
                "ready": True,
                "issues": [{
                    "title": "Add React component",
                    "description": "Create new React component",
                    "size": "S",
                    "tasks": []
                }]
            }),
            make_claude_response({"similar_issues": []}),  # find_similar_issues call
        ]

        mock_github.get_open_issues.return_value = []

        mock_created = MagicMock()
        mock_created.number = 51
        mock_github.create_issue.return_value = mock_created

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["new"], input="Add component\nReact\ny\n")

        assert result.exit_code == 0
        assert "What framework" in result.output
        assert "Created issue #51" in result.output

    def test_new_issue_detects_duplicate(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test duplicate detection during issue creation."""
        mock_claude.side_effect = [
            make_claude_response({
                "ready": True,
                "issues": [{
                    "title": "Fix login bug",
                    "description": "Users cannot login",
                    "size": "S",
                    "tasks": []
                }]
            }),
            make_claude_response({
                "similar_issues": [{
                    "issue_number": 5,
                    "relationship": "duplicate",
                    "reasoning": "Same login issue"
                }]
            }),
        ]

        mock_github.get_open_issues.return_value = [
            Issue(number=5, title="Login broken", body="Cannot login", labels=[])
        ]

        with patch("tshirts.ai._find_claude", return_value="claude"):
            # User declines to create duplicate
            result = cli_runner.invoke(main, ["new"], input="Fix login\nn\n")

        assert result.exit_code == 0
        assert "DUPLICATE" in result.output
        mock_github.create_issue.assert_not_called()

    def test_new_issue_multiple_issues(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test creating multiple distinct issues from one conversation."""
        mock_claude.side_effect = [
            make_claude_response({
                "ready": True,
                "issues": [
                    {"title": "Feature A", "description": "Do A", "size": "S", "tasks": []},
                    {"title": "Feature B", "description": "Do B", "size": "M", "tasks": []},
                ]
            }),
            make_claude_response({"similar_issues": []}),
            make_claude_response({"similar_issues": []}),
        ]

        mock_github.get_open_issues.return_value = []

        mock_issues = [MagicMock(number=60), MagicMock(number=61)]
        mock_github.create_issue.side_effect = mock_issues

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["new"], input="Add features A and B\ny\n")

        assert result.exit_code == 0
        assert mock_github.create_issue.call_count == 2


class TestGroomWorkflow:
    """Integration tests for the groom/refine workflow."""

    def test_groom_list_issues(
        self, cli_runner, mock_github, mock_resolve_repo
    ):
        """Test listing issues that need grooming."""
        mock_github.get_issues_for_grooming.return_value = [
            Issue(number=1, title="Big task", body="Needs refinement", labels=["size: L"]),
            Issue(number=2, title="Medium task", body="Some work", labels=["size: M"]),
        ]

        result = cli_runner.invoke(main, ["groom"])

        assert result.exit_code == 0
        assert "#1" in result.output
        assert "#2" in result.output
        assert "need refinement" in result.output

    def test_groom_refine_issue(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test refining a specific issue."""
        issue = Issue(number=5, title="Vague task", body="Do stuff", labels=["size: M"])
        mock_github.get_issue.return_value = issue

        # Claude asks a question, then provides refined description
        mock_claude.side_effect = [
            make_claude_response({
                "ready": False,
                "question": "What specific stuff needs to be done?",
                "suggestions": []
            }),
            make_claude_response({
                "ready": True,
                "refined_description": "Do X, Y, and Z with proper error handling",
                "suggestions": ["Consider adding tests"]
            }),
        ]

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["groom", "5"], input="X Y and Z\ny\n")

        assert result.exit_code == 0
        assert "What specific stuff" in result.output
        assert "Refined description" in result.output
        mock_github.update_issue_body.assert_called_once()

    def test_refine_alias(
        self, cli_runner, mock_github, mock_resolve_repo
    ):
        """Test that 'refine' is an alias for 'groom'."""
        mock_github.get_issues_for_grooming.return_value = []

        result = cli_runner.invoke(main, ["refine"])

        assert result.exit_code == 0
        assert "No issues need grooming" in result.output


class TestCloseWorkflow:
    """Integration tests for the close workflow."""

    def test_close_with_completed_subtasks(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test closing an issue with all subtasks completed."""
        parent = Issue(number=10, title="Parent Feature", body="Main feature", labels=[])
        mock_github.get_issue.return_value = parent

        # All sub-issues are closed
        mock_github.get_sub_issues.return_value = (
            [],  # open
            [Issue(number=11, title="Sub 1", body="", labels=[]),
             Issue(number=12, title="Sub 2", body="", labels=[])]  # closed
        )

        mock_claude.return_value = make_claude_response({
            "comment": "Feature completed successfully with all subtasks done."
        })

        with patch("tshirts.ai._find_claude", return_value="claude"):
            # Accept subtasks, accept comment, confirm close
            result = cli_runner.invoke(main, ["close", "10"], input="y\na\ny\n")

        assert result.exit_code == 0
        assert "Issue #10 closed" in result.output
        mock_github.close_issue.assert_called_once()

    def test_close_blocked_by_open_subtasks(
        self, cli_runner, mock_github, mock_resolve_repo
    ):
        """Test that close is blocked when subtasks are open."""
        parent = Issue(number=10, title="Parent", body="", labels=[])
        mock_github.get_issue.return_value = parent

        # Has open sub-issues
        mock_github.get_sub_issues.return_value = (
            [Issue(number=11, title="Still open", body="", labels=[])],  # open
            []  # closed
        )

        result = cli_runner.invoke(main, ["close", "10"])

        assert result.exit_code == 1
        assert "Cannot close" in result.output
        assert "open sub-issues" in result.output
        mock_github.close_issue.assert_not_called()

    def test_close_no_subtasks_with_reason(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test closing an issue without subtasks (asks for reason)."""
        issue = Issue(number=20, title="Simple task", body="Just do it", labels=[])
        mock_github.get_issue.return_value = issue
        mock_github.get_sub_issues.return_value = ([], [])  # no sub-issues

        mock_claude.return_value = make_claude_response({
            "comment": "Task completed as requested."
        })

        with patch("tshirts.ai._find_claude", return_value="claude"):
            # Provide reason, accept comment, confirm close
            result = cli_runner.invoke(main, ["close", "20"], input="Done manually\na\ny\n")

        assert result.exit_code == 0
        assert "Issue #20 closed" in result.output

    def test_close_skip_comment(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test closing with skipping the comment."""
        issue = Issue(number=30, title="Task", body="", labels=[])
        mock_github.get_issue.return_value = issue
        mock_github.get_sub_issues.return_value = ([], [])

        mock_claude.return_value = make_claude_response({
            "comment": "Some AI comment"
        })

        with patch("tshirts.ai._find_claude", return_value="claude"):
            # Reason, skip comment, confirm
            result = cli_runner.invoke(main, ["close", "30"], input="Done\ns\ny\n")

        assert result.exit_code == 0
        # close_issue called with None comment
        mock_github.close_issue.assert_called_once_with(issue, None)


class TestErrorRecovery:
    """Integration tests for error handling across components."""

    def test_github_connection_error(self, cli_runner, mock_resolve_repo):
        """Test handling GitHub connection errors."""
        with patch("tshirts.cli.GitHubClient") as MockClient:
            MockClient.side_effect = Exception("Connection failed")

            result = cli_runner.invoke(main, ["estimate"])

        assert result.exit_code != 0

    def test_claude_timeout_recovery(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test recovery from Claude CLI timeout."""
        issue = Issue(number=1, title="Test", body="Body", labels=[])
        mock_github.get_issues_without_size_label.return_value = [issue]

        # Simulate timeout by raising exception
        import subprocess
        mock_claude.side_effect = subprocess.TimeoutExpired("claude", 30)

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate", "--yes"])

        # Should fall back to default size M
        assert result.exit_code == 0
        mock_github.add_size_label.assert_called_once_with(issue, "M")

    def test_invalid_json_recovery(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test recovery from invalid JSON in Claude response."""
        issue = Issue(number=1, title="Test", body="Body", labels=[])
        mock_github.get_issues_without_size_label.return_value = [issue]

        # Return invalid JSON
        bad_result = MagicMock()
        bad_result.returncode = 0
        bad_result.stdout = "This is {not valid} JSON"
        bad_result.stderr = ""
        mock_claude.return_value = bad_result

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["estimate", "--yes"])

        # Should fall back gracefully
        assert result.exit_code == 0
        mock_github.add_size_label.assert_called_once_with(issue, "M")

    def test_partial_claude_response(
        self, cli_runner, mock_github, mock_claude, mock_resolve_repo
    ):
        """Test handling partial/incomplete Claude responses."""
        issue = Issue(number=1, title="Big task", body="Do things", labels=[])
        mock_github.get_issue.return_value = issue

        # Return response missing required fields
        mock_claude.return_value = make_claude_response({
            "tasks": [
                {"title": "Task 1"},  # Missing description and size
                {"description": "Do thing", "size": "S"},  # Missing title
            ]
        })

        mock_created = MagicMock()
        mock_created.number = 10
        mock_github.create_issue.return_value = mock_created

        with patch("tshirts.ai._find_claude", return_value="claude"):
            result = cli_runner.invoke(main, ["breakdown", "1", "--create"])

        # Should handle gracefully with defaults
        assert result.exit_code == 0
        assert mock_github.create_issue.call_count == 2


class TestRepoDetection:
    """Integration tests for repository detection."""

    def test_explicit_repo_flag(self, cli_runner, mock_github):
        """Test using explicit --repo flag."""
        mock_github.get_issues_without_size_label.return_value = []

        with patch("tshirts.cli.GitHubClient") as MockClient:
            MockClient.return_value = mock_github
            result = cli_runner.invoke(main, ["--repo", "owner/repo", "estimate"])

        MockClient.assert_called_once_with("owner/repo")

    def test_repo_from_environment(self, cli_runner, mock_github):
        """Test using TSHIRTS_REPO environment variable."""
        mock_github.get_issues_without_size_label.return_value = []

        with patch("tshirts.cli.GitHubClient") as MockClient:
            MockClient.return_value = mock_github
            result = cli_runner.invoke(
                main, ["estimate"],
                env={"TSHIRTS_REPO": "env/repo"}
            )

        MockClient.assert_called_once_with("env/repo")

    def test_repo_from_git_remote(self, cli_runner, mock_github):
        """Test detecting repo from git remote."""
        mock_github.get_issues_without_size_label.return_value = []

        with patch("tshirts.cli.GitHubClient") as MockClient:
            MockClient.return_value = mock_github
            with patch("tshirts.cli.detect_repo_from_git", return_value="git/repo"):
                result = cli_runner.invoke(main, ["estimate"])

        MockClient.assert_called_once_with("git/repo")
