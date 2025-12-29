"""Tests for error handling and edge cases."""

import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from tshirts.github_client import Issue, GitHubClient
from tshirts.ai import (
    _find_claude,
    _call_claude,
    estimate_issue_size,
    breakdown_issue,
    draft_issue_conversation,
    groom_issue_conversation,
    find_similar_issues,
    generate_closing_comment,
    DraftIssue,
)


class TestClaudeCLINotFound:
    """Tests for Claude CLI not found scenarios."""

    def test_find_claude_raises_when_not_found(self):
        """Test _find_claude raises FileNotFoundError when CLI not found."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="claude CLI not found"):
                _find_claude()

    def test_find_claude_finds_claude(self):
        """Test _find_claude returns path when found."""
        with patch("shutil.which", side_effect=["/usr/bin/claude", None]):
            result = _find_claude()
        assert result == "/usr/bin/claude"

    def test_find_claude_finds_claude_cmd_on_windows(self):
        """Test _find_claude finds claude.cmd on Windows."""
        with patch("shutil.which", side_effect=[None, "C:\\npm\\claude.cmd"]):
            result = _find_claude()
        assert result == "C:\\npm\\claude.cmd"

    def test_estimate_handles_cli_not_found(self):
        """Test estimate gracefully handles missing CLI."""
        with patch("tshirts.ai._find_claude", side_effect=FileNotFoundError("not found")):
            issue = Issue(number=1, title="Test", body="", labels=[])
            # Should raise since we can't call Claude
            with pytest.raises(FileNotFoundError):
                estimate_issue_size(issue)


class TestSubprocessExitCodes:
    """Tests for subprocess non-zero exit code handling."""

    def test_call_claude_with_nonzero_exit(self):
        """Test _call_claude handles non-zero exit codes."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 1

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", return_value=mock_result):
                result = _call_claude("test", schema=None)

        # Should return empty string, not crash
        assert result == ""

    def test_estimate_defaults_on_subprocess_error(self):
        """Test estimate returns default on CalledProcessError."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_breakdown_returns_fallback_on_subprocess_error(self):
        """Test breakdown returns fallback task on error."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
                issue = Issue(number=1, title="My Feature", body="Description", labels=[])
                result = breakdown_issue(issue)

        assert len(result) == 1
        assert "My Feature" in result[0].title

    def test_conversation_handles_subprocess_error(self):
        """Test conversation returns fallback on error."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
                ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert ready is False
        assert question is not None
        assert drafts is None

    def test_groom_handles_subprocess_error(self):
        """Test groom returns fallback on error."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
                issue = Issue(number=1, title="Test", body="", labels=[])
                ready, question, refined, suggestions = groom_issue_conversation(issue, [])

        assert ready is False
        assert question is not None

    def test_similar_issues_returns_empty_on_error(self):
        """Test similar issues returns empty list on error."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
                draft = DraftIssue(title="Test", description="", size="M", tasks=[])
                existing = [Issue(number=1, title="Other", body="", labels=[])]
                result = find_similar_issues(draft, existing)

        assert result == []

    def test_closing_comment_returns_fallback_on_error(self):
        """Test closing comment returns fallback on error."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = generate_closing_comment(issue, [])

        assert "closed" in result.lower()


class TestSubprocessTimeout:
    """Tests for subprocess timeout handling."""

    def test_estimate_handles_timeout(self):
        """Test estimate handles subprocess timeout."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 30)):
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_breakdown_handles_timeout(self):
        """Test breakdown handles subprocess timeout."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 30)):
                issue = Issue(number=1, title="Test", body="Body", labels=[])
                result = breakdown_issue(issue)

        assert len(result) == 1

    def test_conversation_handles_timeout(self):
        """Test conversation handles subprocess timeout."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 30)):
                ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert ready is False


class TestMalformedJSONResponses:
    """Tests for malformed JSON response handling."""

    def test_handles_truncated_json(self):
        """Test handling of truncated JSON."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout='{"size": "M"')  # Missing closing brace
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"  # Default fallback

    def test_handles_json_with_trailing_garbage(self):
        """Test handling JSON with trailing garbage."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout='{"size": "L"}extra garbage')
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"  # Default due to parse error

    def test_handles_nested_invalid_json(self):
        """Test handling nested invalid JSON."""
        response = '{"structured_output": {"size": undefined}}'  # undefined is not valid JSON

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=response)
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_handles_json_array_instead_of_object(self):
        """Test handling JSON array when object expected."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout='["XS", "S", "M"]')
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_handles_json_string_instead_of_object(self):
        """Test handling JSON string when object expected."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout='"just a string"')
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_handles_deeply_nested_null(self):
        """Test handling deeply nested null values."""
        response = json.dumps({
            "structured_output": {
                "tasks": [
                    {"title": None, "description": None, "size": None}
                ]
            }
        })

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=response)
                issue = Issue(number=1, title="Test", body="Body", labels=[])
                result = breakdown_issue(issue)

        # Should handle gracefully (may return fallback or handle nulls)
        assert isinstance(result, list)


class TestEmptyResponses:
    """Tests for empty and whitespace response handling."""

    def test_handles_empty_string(self):
        """Test handling empty string response."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="")
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_handles_whitespace_only(self):
        """Test handling whitespace-only response."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="   \n\t  \n  ")
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_handles_newlines_only(self):
        """Test handling newlines-only response."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="\n\n\n")
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"

    def test_breakdown_handles_empty_response(self):
        """Test breakdown with empty response returns fallback."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="")
                issue = Issue(number=1, title="Feature X", body="Desc", labels=[])
                result = breakdown_issue(issue)

        assert len(result) == 1
        assert "Feature X" in result[0].title


class TestTypeErrors:
    """Tests for type error handling during parsing."""

    def test_handles_size_as_integer(self):
        """Test handling size returned as integer instead of string."""
        response = json.dumps({"structured_output": {"size": 3}})

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=response)
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        # Should handle gracefully
        assert result in ["M", 3]  # Either default or the raw value

    def test_handles_tasks_as_string(self):
        """Test handling tasks returned as string instead of array."""
        response = json.dumps({"structured_output": {"tasks": "not an array"}})

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=response)
                issue = Issue(number=1, title="Test", body="Body", labels=[])
                result = breakdown_issue(issue)

        # Should return fallback
        assert len(result) == 1

    def test_handles_ready_as_string(self):
        """Test handling ready returned as string instead of boolean."""
        response = json.dumps({"structured_output": {"ready": "true", "question": "Q?"}})

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=response)
                ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        # Python considers non-empty string as truthy
        assert isinstance(ready, (bool, str))


class TestGitHubAPIErrors:
    """Tests for GitHub API error handling."""

    def test_client_init_without_token(self):
        """Test GitHubClient raises without GITHUB_TOKEN."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                GitHubClient("owner/repo")

    def test_get_issue_handles_not_found(self):
        """Test get_issue returns None for non-existent issue."""
        from github import GithubException

        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = []
        mock_repo.get_issue.side_effect = GithubException(404, "Not Found", None)

        mock_gh = MagicMock()
        mock_gh.get_repo.return_value = mock_repo

        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake"}):
            with patch("tshirts.github_client.Github", return_value=mock_gh):
                client = GitHubClient("owner/repo")
                result = client.get_issue(999)

        assert result is None

    def test_add_size_label_invalid_size(self):
        """Test add_size_label raises for invalid size."""
        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = []

        mock_gh = MagicMock()
        mock_gh.get_repo.return_value = mock_repo

        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake"}):
            with patch("tshirts.github_client.Github", return_value=mock_gh):
                client = GitHubClient("owner/repo")
                issue = Issue(number=1, title="Test", body="", labels=[])

                with pytest.raises(ValueError, match="Invalid size"):
                    client.add_size_label(issue, "XXXL")


class TestEdgeCaseInputs:
    """Tests for edge case inputs."""

    def test_issue_with_extremely_long_body(self):
        """Test handling issue with very long body."""
        long_body = "x" * 100000  # 100KB body

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=json.dumps({"structured_output": {"size": "XL"}}))
                issue = Issue(number=1, title="Test", body=long_body, labels=[])
                result = estimate_issue_size(issue)

        assert result == "XL"

    def test_issue_with_binary_like_content(self):
        """Test handling issue with binary-like content in body."""
        binary_like = "\x00\x01\x02\x03"

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=json.dumps({"structured_output": {"size": "S"}}))
                issue = Issue(number=1, title="Test", body=binary_like, labels=[])
                result = estimate_issue_size(issue)

        assert result == "S"

    def test_conversation_with_empty_history(self):
        """Test conversation with empty history."""
        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=json.dumps({
                    "structured_output": {"ready": False, "question": "What do you need?"}
                }))
                ready, question, drafts = draft_issue_conversation([])

        assert ready is False
        assert question is not None

    def test_similar_issues_with_empty_existing(self):
        """Test similar issues with no existing issues."""
        draft = DraftIssue(title="New", description="Desc", size="M", tasks=[])
        result = find_similar_issues(draft, [])

        assert result == []

    def test_closing_comment_with_many_sub_issues(self):
        """Test closing comment with many sub-issues."""
        sub_issues = [
            Issue(number=i, title=f"Sub {i}", body="", labels=[])
            for i in range(50)
        ]

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=json.dumps({
                    "structured_output": {"comment": "All 50 tasks complete!"}
                }))
                issue = Issue(number=1, title="Parent", body="", labels=[])
                result = generate_closing_comment(issue, sub_issues)

        assert "50" in result or "complete" in result.lower()


class TestStderrHandling:
    """Tests for stderr output handling."""

    def test_call_claude_ignores_stderr(self):
        """Test that stderr doesn't affect result parsing."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"structured_output": {"size": "L"}})
        mock_result.stderr = "Warning: something happened"

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", return_value=mock_result):
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "L"

    def test_handles_stderr_with_empty_stdout(self):
        """Test handling when stderr has content but stdout is empty."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error: API rate limit exceeded"

        with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
            with patch("subprocess.run", return_value=mock_result):
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

        assert result == "M"  # Default fallback
