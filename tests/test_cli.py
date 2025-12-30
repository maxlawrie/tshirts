"""Tests for the CLI module."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from tshirts.cli import (
    main,
    detect_repo_from_git,
    resolve_repo,
    select_repo_interactive,
)
from tshirts.github_client import Issue
from tshirts.ai import SubTask, DraftIssue


@pytest.fixture
def cli_runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_github_client():
    """Mock GitHubClient for CLI tests."""
    with patch("tshirts.cli.GitHubClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def sample_issue():
    """Sample Issue for testing."""
    return Issue(number=1, title="Test Issue", body="Description", labels=["size: M"])


class TestDetectRepoFromGit:
    """Tests for detect_repo_from_git function."""

    def test_detects_https_url(self):
        """Test parsing HTTPS GitHub URL."""
        mock_result = MagicMock()
        mock_result.stdout = "https://github.com/owner/repo.git\n"

        with patch("subprocess.run", return_value=mock_result):
            result = detect_repo_from_git()

        assert result == "owner/repo"

    def test_detects_ssh_url(self):
        """Test parsing SSH GitHub URL."""
        mock_result = MagicMock()
        mock_result.stdout = "git@github.com:owner/repo.git\n"

        with patch("subprocess.run", return_value=mock_result):
            result = detect_repo_from_git()

        assert result == "owner/repo"

    def test_handles_url_without_git_suffix(self):
        """Test URL without .git suffix."""
        mock_result = MagicMock()
        mock_result.stdout = "https://github.com/owner/repo\n"

        with patch("subprocess.run", return_value=mock_result):
            result = detect_repo_from_git()

        assert result == "owner/repo"

    def test_returns_none_on_error(self):
        """Test that errors return None."""
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = detect_repo_from_git()

        assert result is None

    def test_returns_none_for_non_github_url(self):
        """Test non-GitHub URLs return None."""
        mock_result = MagicMock()
        mock_result.stdout = "https://gitlab.com/owner/repo.git\n"

        with patch("subprocess.run", return_value=mock_result):
            result = detect_repo_from_git()

        assert result is None


class TestResolveRepo:
    """Tests for resolve_repo function."""

    def test_returns_provided_repo(self):
        """Test that provided repo is returned directly."""
        result = resolve_repo("owner/repo")
        assert result == "owner/repo"

    def test_detects_from_git(self):
        """Test falling back to git detection."""
        with patch("tshirts.cli.detect_repo_from_git", return_value="detected/repo"):
            result = resolve_repo(None)

        assert result == "detected/repo"

    def test_falls_back_to_interactive(self):
        """Test falling back to interactive selection."""
        with patch("tshirts.cli.detect_repo_from_git", return_value=None):
            with patch("tshirts.cli.select_repo_interactive", return_value="selected/repo"):
                result = resolve_repo(None)

        assert result == "selected/repo"


class TestMainGroup:
    """Tests for the main CLI group."""

    def test_help_output(self, cli_runner):
        """Test that help displays correctly."""
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "tshirts" in result.output
        assert "--repo" in result.output

    def test_repo_option_passed_to_context(self, cli_runner):
        """Test --repo option is stored in context."""
        with patch("tshirts.cli.GitHubClient") as mock_client:
            mock_client.return_value.get_issues_without_size_label.return_value = []
            result = cli_runner.invoke(main, ["--repo", "owner/repo", "estimate"])

        mock_client.assert_called_with("owner/repo")


class TestEstimateCommand:
    """Tests for the estimate command."""

    def test_no_issues_without_labels(self, cli_runner, mock_github_client):
        """Test message when all issues have labels."""
        mock_github_client.get_issues_without_size_label.return_value = []

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["estimate"])

        assert result.exit_code == 0
        assert "already have size labels" in result.output

    def test_estimates_and_labels_issues_with_yes_flag(self, cli_runner, mock_github_client, sample_issue):
        """Test estimating and labeling issues with --yes flag (auto-accept)."""
        issue_no_label = Issue(number=1, title="Test", body="Body", labels=[])
        mock_github_client.get_issues_without_size_label.return_value = [issue_no_label]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.estimate_issue_size", return_value="M"):
                result = cli_runner.invoke(main, ["estimate", "--yes"])

        assert result.exit_code == 0
        assert "Suggested: M" in result.output
        assert "Labeled M" in result.output
        mock_github_client.add_size_label.assert_called_once()

    def test_estimates_interactive_accept(self, cli_runner, mock_github_client, sample_issue):
        """Test interactive mode - accepting suggested size."""
        issue_no_label = Issue(number=1, title="Test", body="Body", labels=[])
        mock_github_client.get_issues_without_size_label.return_value = [issue_no_label]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.estimate_issue_size", return_value="M"):
                result = cli_runner.invoke(main, ["estimate"], input="a\n")

        assert result.exit_code == 0
        assert "Suggested: M" in result.output
        mock_github_client.add_size_label.assert_called_once()

    def test_estimates_interactive_skip(self, cli_runner, mock_github_client, sample_issue):
        """Test interactive mode - skipping an issue."""
        issue_no_label = Issue(number=1, title="Test", body="Body", labels=[])
        mock_github_client.get_issues_without_size_label.return_value = [issue_no_label]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.estimate_issue_size", return_value="M"):
                result = cli_runner.invoke(main, ["estimate"], input="s\n")

        assert result.exit_code == 0
        assert "Skipped" in result.output
        assert "0 labeled, 1 skipped" in result.output
        mock_github_client.add_size_label.assert_not_called()

    def test_estimates_interactive_change(self, cli_runner, mock_github_client, sample_issue):
        """Test interactive mode - changing the suggested size."""
        issue_no_label = Issue(number=1, title="Test", body="Body", labels=[])
        mock_github_client.get_issues_without_size_label.return_value = [issue_no_label]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.estimate_issue_size", return_value="M"):
                result = cli_runner.invoke(main, ["estimate"], input="c\nL\n")

        assert result.exit_code == 0
        assert "Labeled L" in result.output
        mock_github_client.add_size_label.assert_called_once()


class TestBreakdownCommand:
    """Tests for the breakdown command."""

    def test_issue_not_found(self, cli_runner, mock_github_client):
        """Test error when issue not found."""
        mock_github_client.get_issue.return_value = None

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["breakdown", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_breakdown_with_create_flag(self, cli_runner, mock_github_client, sample_issue):
        """Test breakdown with --create flag creates issues immediately."""
        mock_github_client.get_issue.return_value = sample_issue

        mock_new_issue = MagicMock()
        mock_new_issue.number = 10
        mock_github_client.create_issue.return_value = mock_new_issue

        tasks = [
            SubTask(title="Task 1", description="Do thing 1", size="S"),
            SubTask(title="Task 2", description="Do thing 2", size="XS"),
        ]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.breakdown_issue", return_value=tasks):
                result = cli_runner.invoke(main, ["breakdown", "1", "--create"])

        assert result.exit_code == 0
        assert "Created" in result.output
        assert mock_github_client.create_issue.call_count == 2

    def test_breakdown_quit_without_create(self, cli_runner, mock_github_client, sample_issue):
        """Test quitting breakdown without creating issues."""
        mock_github_client.get_issue.return_value = sample_issue

        tasks = [SubTask(title="Task 1", description="Desc", size="S")]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.breakdown_issue", return_value=tasks):
                result = cli_runner.invoke(main, ["breakdown", "1"], input="q\n")

        assert result.exit_code == 0
        assert "without creating" in result.output
        mock_github_client.create_issue.assert_not_called()

    def test_breakdown_create_selected(self, cli_runner, mock_github_client, sample_issue):
        """Test creating selected issues from menu."""
        mock_github_client.get_issue.return_value = sample_issue

        mock_new_issue = MagicMock()
        mock_new_issue.number = 10
        mock_github_client.create_issue.return_value = mock_new_issue

        tasks = [SubTask(title="Task 1", description="Desc", size="S")]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.breakdown_issue", return_value=tasks):
                result = cli_runner.invoke(main, ["breakdown", "1"], input="c\n")

        assert result.exit_code == 0
        assert "Created" in result.output


class TestNewCommand:
    """Tests for the new command."""

    def test_new_creates_issue(self, cli_runner, mock_github_client):
        """Test new command creates issue after conversation."""
        mock_new_issue = MagicMock()
        mock_new_issue.number = 42
        mock_github_client.create_issue.return_value = mock_new_issue
        mock_github_client.get_open_issues.return_value = []

        draft = DraftIssue(
            title="New Feature",
            description="Implement feature",
            size="M",
            tasks=["Task 1"]
        )

        # Simulate: AI is ready immediately
        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.draft_issue_conversation", return_value=(True, None, [draft])):
                with patch("tshirts.cli.find_similar_issues", return_value=[]):
                    result = cli_runner.invoke(main, ["new"], input="Add a feature\ny\n")

        assert result.exit_code == 0
        assert "Created issue #42" in result.output

    def test_new_asks_questions(self, cli_runner, mock_github_client):
        """Test new command asks follow-up questions."""
        draft = DraftIssue(title="Feature", description="Desc", size="S", tasks=[])

        mock_new_issue = MagicMock()
        mock_new_issue.number = 1
        mock_github_client.create_issue.return_value = mock_new_issue
        mock_github_client.get_open_issues.return_value = []

        # First call: not ready, ask question. Second call: ready
        call_count = [0]
        def mock_conversation(conv):
            call_count[0] += 1
            if call_count[0] == 1:
                return (False, "What problem does this solve?", None)
            return (True, None, [draft])

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.draft_issue_conversation", side_effect=mock_conversation):
                with patch("tshirts.cli.find_similar_issues", return_value=[]):
                    result = cli_runner.invoke(main, ["new"], input="feature\nIt solves X\ny\n")

        assert "What problem does this solve?" in result.output

    def test_new_declines_creation(self, cli_runner, mock_github_client):
        """Test declining to create issues."""
        draft = DraftIssue(title="Feature", description="Desc", size="S", tasks=[])
        mock_github_client.get_open_issues.return_value = []

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.draft_issue_conversation", return_value=(True, None, [draft])):
                with patch("tshirts.cli.find_similar_issues", return_value=[]):
                    result = cli_runner.invoke(main, ["new"], input="feature\nn\n")

        assert "not created" in result.output
        mock_github_client.create_issue.assert_not_called()


class TestGroomCommand:
    """Tests for the groom command."""

    def test_groom_lists_issues_without_number(self, cli_runner, mock_github_client, sample_issue):
        """Test groom without issue number lists groomable issues."""
        mock_github_client.get_issues_for_grooming.return_value = [sample_issue]

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["groom"])

        assert result.exit_code == 0
        assert "may need refinement" in result.output
        assert "#1" in result.output

    def test_groom_no_issues(self, cli_runner, mock_github_client):
        """Test groom with no groomable issues."""
        mock_github_client.get_issues_for_grooming.return_value = []

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["groom"])

        assert result.exit_code == 0
        assert "No issues need grooming" in result.output

    def test_groom_issue_not_found(self, cli_runner, mock_github_client):
        """Test groom with non-existent issue."""
        mock_github_client.get_issue.return_value = None

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["groom", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_groom_updates_issue(self, cli_runner, mock_github_client, sample_issue):
        """Test groom updates issue with refined description."""
        mock_github_client.get_issue.return_value = sample_issue

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.groom_issue_conversation", return_value=(True, None, "Refined description", [])):
                result = cli_runner.invoke(main, ["groom", "1"], input="y\n")

        assert result.exit_code == 0
        assert "updated" in result.output
        mock_github_client.update_issue_body.assert_called_once()

    def test_groom_declines_update(self, cli_runner, mock_github_client, sample_issue):
        """Test declining groom update."""
        mock_github_client.get_issue.return_value = sample_issue

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.groom_issue_conversation", return_value=(True, None, "Refined", [])):
                result = cli_runner.invoke(main, ["groom", "1"], input="n\n")

        assert "not updated" in result.output
        mock_github_client.update_issue_body.assert_not_called()


class TestRefineCommand:
    """Tests for the refine command (alias for groom)."""

    def test_refine_invokes_groom(self, cli_runner, mock_github_client, sample_issue):
        """Test that refine calls groom with same arguments."""
        mock_github_client.get_issue.return_value = sample_issue

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.groom_issue_conversation", return_value=(True, None, "Refined", [])):
                result = cli_runner.invoke(main, ["refine", "1"], input="y\n")

        assert result.exit_code == 0
        mock_github_client.update_issue_body.assert_called_once()


class TestCloseCommand:
    """Tests for the close command."""

    def test_close_issue_not_found(self, cli_runner, mock_github_client):
        """Test error when issue not found."""
        mock_github_client.get_issue.return_value = None

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["close", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_close_blocks_with_open_sub_issues(self, cli_runner, mock_github_client, sample_issue):
        """Test close is blocked when sub-issues are open."""
        mock_github_client.get_issue.return_value = sample_issue
        open_sub = Issue(number=2, title="Open Sub", body="", labels=[])
        mock_github_client.get_sub_issues.return_value = ([open_sub], [])

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            result = cli_runner.invoke(main, ["close", "1"])

        assert result.exit_code == 1
        assert "Cannot close" in result.output
        assert "open sub-issues" in result.output

    def test_close_with_all_subs_closed(self, cli_runner, mock_github_client, sample_issue):
        """Test closing when all sub-issues are closed."""
        mock_github_client.get_issue.return_value = sample_issue
        closed_sub = Issue(number=2, title="Closed Sub", body="", labels=[])
        mock_github_client.get_sub_issues.return_value = ([], [closed_sub])

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.generate_closing_comment", return_value="All done!"):
                # y = satisfied, a = accept comment, y = confirm close
                result = cli_runner.invoke(main, ["close", "1"], input="y\na\ny\n")

        assert result.exit_code == 0
        assert "closed" in result.output.lower()
        mock_github_client.close_issue.assert_called_once()

    def test_close_without_sub_issues(self, cli_runner, mock_github_client, sample_issue):
        """Test closing issue with no sub-issues asks for reason."""
        mock_github_client.get_issue.return_value = sample_issue
        mock_github_client.get_sub_issues.return_value = ([], [])

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.generate_closing_comment", return_value="Done!"):
                # "Completed" = reason, a = accept comment, y = confirm
                result = cli_runner.invoke(main, ["close", "1"], input="Completed\na\ny\n")

        assert result.exit_code == 0
        mock_github_client.close_issue.assert_called_once()

    def test_close_skip_comment(self, cli_runner, mock_github_client, sample_issue):
        """Test closing with skipped comment."""
        mock_github_client.get_issue.return_value = sample_issue
        mock_github_client.get_sub_issues.return_value = ([], [])

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.generate_closing_comment", return_value="Done!"):
                # reason, s = skip comment, y = confirm
                result = cli_runner.invoke(main, ["close", "1"], input="Done\ns\ny\n")

        assert result.exit_code == 0
        # close_issue called with None comment
        mock_github_client.close_issue.assert_called_once_with(sample_issue, None)

    def test_close_abort_confirmation(self, cli_runner, mock_github_client, sample_issue):
        """Test aborting close at final confirmation."""
        mock_github_client.get_issue.return_value = sample_issue
        mock_github_client.get_sub_issues.return_value = ([], [])

        with patch("tshirts.cli.resolve_repo", return_value="owner/repo"):
            with patch("tshirts.cli.generate_closing_comment", return_value="Done!"):
                # reason, a = accept, n = abort
                result = cli_runner.invoke(main, ["close", "1"], input="Done\na\nn\n")

        assert "Aborting" in result.output
        mock_github_client.close_issue.assert_not_called()


class TestRepoOverride:
    """Tests for --repo option handling."""

    def test_repo_from_env_var(self, cli_runner, mock_github_client):
        """Test repo from TSHIRTS_REPO environment variable."""
        mock_github_client.get_issues_without_size_label.return_value = []

        result = cli_runner.invoke(main, ["estimate"], env={"TSHIRTS_REPO": "env/repo"})

        from tshirts.cli import GitHubClient
        # The mock was called - check it received the env repo
        assert result.exit_code == 0

    def test_cli_option_overrides_env(self, cli_runner):
        """Test --repo option overrides environment variable."""
        with patch("tshirts.cli.GitHubClient") as mock_client:
            mock_client.return_value.get_issues_without_size_label.return_value = []

            result = cli_runner.invoke(
                main,
                ["--repo", "cli/repo", "estimate"],
                env={"TSHIRTS_REPO": "env/repo"}
            )

        mock_client.assert_called_with("cli/repo")
