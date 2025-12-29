"""Tests for JSON schema handling and response parsing."""

import json
import pytest
from unittest.mock import patch, MagicMock

from tshirts.github_client import Issue
from tshirts.ai import (
    _call_claude,
    estimate_issue_size,
    breakdown_issue,
    draft_issue_conversation,
    groom_issue_conversation,
    find_similar_issues,
    generate_closing_comment,
    DraftIssue,
    SIZE_SCHEMA,
    BREAKDOWN_SCHEMA,
    CONVERSATION_SCHEMA,
    GROOM_SCHEMA,
    SIMILAR_ISSUES_SCHEMA,
    CLOSING_COMMENT_SCHEMA,
)


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for testing _call_claude."""
    with patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def patch_claude_finder():
    """Patch the claude CLI finder."""
    with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
        yield


class TestCallClaudeSchemaFlag:
    """Tests for _call_claude passing --json-schema correctly."""

    def test_passes_json_schema_flag(self, mock_subprocess, patch_claude_finder):
        """Test that --json-schema is passed when schema provided."""
        mock_subprocess.return_value = MagicMock(stdout="{}")

        _call_claude("test prompt", schema='{"type": "object"}')

        call_args = mock_subprocess.call_args
        cmd = call_args[0][0]
        assert "--json-schema" in cmd
        assert '{"type": "object"}' in cmd

    def test_passes_output_format_json(self, mock_subprocess, patch_claude_finder):
        """Test that --output-format json is passed with schema."""
        mock_subprocess.return_value = MagicMock(stdout="{}")

        _call_claude("test prompt", schema='{"type": "object"}')

        cmd = mock_subprocess.call_args[0][0]
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_no_schema_flag_without_schema(self, mock_subprocess, patch_claude_finder):
        """Test that --json-schema is NOT passed when no schema."""
        mock_subprocess.return_value = MagicMock(stdout="response")

        _call_claude("test prompt", schema=None)

        cmd = mock_subprocess.call_args[0][0]
        assert "--json-schema" not in cmd
        assert "--output-format" not in cmd

    def test_prompt_passed_via_stdin(self, mock_subprocess, patch_claude_finder):
        """Test that prompt is passed via stdin input."""
        mock_subprocess.return_value = MagicMock(stdout="{}")

        _call_claude("multi\nline\nprompt", schema=None)

        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs["input"] == "multi\nline\nprompt"

    def test_uses_sonnet_model(self, mock_subprocess, patch_claude_finder):
        """Test that sonnet model is specified."""
        mock_subprocess.return_value = MagicMock(stdout="{}")

        _call_claude("test", schema=None)

        cmd = mock_subprocess.call_args[0][0]
        assert "--model" in cmd
        assert "sonnet" in cmd


class TestSizeSchemaResponseParsing:
    """Tests for parsing SIZE_SCHEMA responses."""

    def test_parses_valid_size_response(self, patch_claude_finder):
        """Test parsing valid size response."""
        response = {"structured_output": {"size": "L"}}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = estimate_issue_size(issue)

        assert result == "L"

    def test_parses_all_valid_sizes(self, patch_claude_finder):
        """Test all valid size values are accepted."""
        for size in ["XS", "S", "M", "L", "XL"]:
            response = {"structured_output": {"size": size}}

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout=json.dumps(response))
                issue = Issue(number=1, title="Test", body="", labels=[])
                result = estimate_issue_size(issue)

            assert result == size

    def test_handles_direct_size_field(self, patch_claude_finder):
        """Test fallback parsing when size is directly in response."""
        response = {"size": "S"}  # No structured_output wrapper

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = estimate_issue_size(issue)

        assert result == "S"

    def test_defaults_on_missing_size(self, patch_claude_finder):
        """Test default to M when size field missing."""
        response = {"structured_output": {}}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = estimate_issue_size(issue)

        assert result == "M"


class TestBreakdownSchemaResponseParsing:
    """Tests for parsing BREAKDOWN_SCHEMA responses."""

    def test_parses_valid_breakdown_response(self, patch_claude_finder):
        """Test parsing valid breakdown with tasks."""
        response = {
            "structured_output": {
                "tasks": [
                    {"title": "Task 1", "description": "Desc 1", "size": "S"},
                    {"title": "Task 2", "description": "Desc 2", "size": "M"},
                ]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = breakdown_issue(issue)

        assert len(result) == 2
        assert result[0].title == "Task 1"
        assert result[0].size == "S"
        assert result[1].title == "Task 2"

    def test_normalizes_size_to_uppercase(self, patch_claude_finder):
        """Test that lowercase sizes are normalized."""
        response = {
            "structured_output": {
                "tasks": [{"title": "Task", "description": "Desc", "size": "xs"}]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = breakdown_issue(issue)

        assert result[0].size == "XS"

    def test_handles_empty_tasks_array(self, patch_claude_finder):
        """Test handling of empty tasks array."""
        response = {"structured_output": {"tasks": []}}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = breakdown_issue(issue)

        assert result == []

    def test_handles_direct_tasks_field(self, patch_claude_finder):
        """Test fallback when tasks is directly in response."""
        response = {
            "tasks": [{"title": "Task", "description": "Desc", "size": "M"}]
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = breakdown_issue(issue)

        assert len(result) == 1


class TestConversationSchemaResponseParsing:
    """Tests for parsing CONVERSATION_SCHEMA responses."""

    def test_parses_not_ready_response(self, patch_claude_finder):
        """Test parsing when not ready with question."""
        response = {
            "structured_output": {
                "ready": False,
                "question": "What framework?"
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert ready is False
        assert question == "What framework?"
        assert drafts is None

    def test_parses_ready_response_with_issues(self, patch_claude_finder):
        """Test parsing when ready with draft issues."""
        response = {
            "structured_output": {
                "ready": True,
                "issues": [
                    {
                        "title": "Feature A",
                        "description": "Implement A",
                        "size": "M",
                        "tasks": ["Task 1", "Task 2"]
                    }
                ]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert ready is True
        assert question is None
        assert len(drafts) == 1
        assert drafts[0].title == "Feature A"
        assert drafts[0].tasks == ["Task 1", "Task 2"]

    def test_parses_multiple_draft_issues(self, patch_claude_finder):
        """Test parsing multiple draft issues."""
        response = {
            "structured_output": {
                "ready": True,
                "issues": [
                    {"title": "Issue 1", "description": "Desc 1", "size": "S", "tasks": []},
                    {"title": "Issue 2", "description": "Desc 2", "size": "M", "tasks": []},
                    {"title": "Issue 3", "description": "Desc 3", "size": "L", "tasks": []},
                ]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert len(drafts) == 3

    def test_handles_missing_optional_fields(self, patch_claude_finder):
        """Test handling when optional fields are missing."""
        response = {
            "structured_output": {
                "ready": True,
                "issues": [{"title": "Minimal"}]  # Missing description, size, tasks
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert drafts[0].title == "Minimal"
        assert drafts[0].description == ""
        assert drafts[0].size == "M"
        assert drafts[0].tasks == []


class TestGroomSchemaResponseParsing:
    """Tests for parsing GROOM_SCHEMA responses."""

    def test_parses_not_ready_with_question(self, patch_claude_finder):
        """Test parsing groom not ready response."""
        response = {
            "structured_output": {
                "ready": False,
                "question": "What are the acceptance criteria?",
                "suggestions": []
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            ready, question, refined, suggestions = groom_issue_conversation(issue, [])

        assert ready is False
        assert question == "What are the acceptance criteria?"
        assert refined is None

    def test_parses_ready_with_refined_description(self, patch_claude_finder):
        """Test parsing groom ready response."""
        response = {
            "structured_output": {
                "ready": True,
                "refined_description": "Improved description with details.",
                "suggestions": ["Consider breaking down"]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            ready, question, refined, suggestions = groom_issue_conversation(issue, [])

        assert ready is True
        assert refined == "Improved description with details."
        assert suggestions == ["Consider breaking down"]

    def test_handles_empty_suggestions(self, patch_claude_finder):
        """Test handling empty suggestions array."""
        response = {
            "structured_output": {
                "ready": True,
                "refined_description": "Refined",
                "suggestions": []
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            _, _, _, suggestions = groom_issue_conversation(issue, [])

        assert suggestions == []


class TestSimilarIssuesSchemaResponseParsing:
    """Tests for parsing SIMILAR_ISSUES_SCHEMA responses."""

    def test_parses_similar_issues(self, patch_claude_finder):
        """Test parsing similar issues response."""
        response = {
            "structured_output": {
                "similar_issues": [
                    {"issue_number": 10, "relationship": "duplicate", "reasoning": "Same feature"},
                    {"issue_number": 20, "relationship": "related", "reasoning": "Similar area"},
                ]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            draft = DraftIssue(title="Test", description="Desc", size="M", tasks=[])
            existing = [
                Issue(number=10, title="Existing 1", body="", labels=[]),
                Issue(number=20, title="Existing 2", body="", labels=[]),
            ]
            result = find_similar_issues(draft, existing)

        assert len(result) == 2
        assert result[0].issue_number == 10
        assert result[0].relationship == "duplicate"
        assert result[1].issue_number == 20

    def test_filters_out_distinct_issues(self, patch_claude_finder):
        """Test that distinct relationships are filtered out."""
        response = {
            "structured_output": {
                "similar_issues": [
                    {"issue_number": 10, "relationship": "distinct", "reasoning": "Not related"},
                ]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            draft = DraftIssue(title="Test", description="", size="M", tasks=[])
            existing = [Issue(number=10, title="Other", body="", labels=[])]
            result = find_similar_issues(draft, existing)

        assert len(result) == 0

    def test_filters_out_unknown_issue_numbers(self, patch_claude_finder):
        """Test that non-existent issue numbers are filtered."""
        response = {
            "structured_output": {
                "similar_issues": [
                    {"issue_number": 999, "relationship": "duplicate", "reasoning": "Hallucinated"},
                ]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            draft = DraftIssue(title="Test", description="", size="M", tasks=[])
            existing = [Issue(number=1, title="Real", body="", labels=[])]
            result = find_similar_issues(draft, existing)

        assert len(result) == 0


class TestClosingCommentSchemaResponseParsing:
    """Tests for parsing CLOSING_COMMENT_SCHEMA responses."""

    def test_parses_comment_response(self, patch_claude_finder):
        """Test parsing closing comment response."""
        response = {
            "structured_output": {
                "comment": "This issue has been resolved. Thanks for the contribution!"
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = generate_closing_comment(issue, [])

        assert result == "This issue has been resolved. Thanks for the contribution!"

    def test_defaults_on_missing_comment(self, patch_claude_finder):
        """Test default comment when field missing."""
        response = {"structured_output": {}}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = generate_closing_comment(issue, [])

        assert result == "Issue closed."


class TestSchemaValidationErrorHandling:
    """Tests for handling schema validation errors and malformed responses."""

    def test_estimate_handles_invalid_json(self, patch_claude_finder):
        """Test estimate handles non-JSON response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not valid json")
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = estimate_issue_size(issue)

        assert result == "M"  # Default fallback

    def test_breakdown_handles_invalid_json(self, patch_claude_finder):
        """Test breakdown handles non-JSON response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not valid json")
            issue = Issue(number=1, title="Test", body="Body", labels=[])
            result = breakdown_issue(issue)

        assert len(result) == 1
        assert "Test" in result[0].title

    def test_conversation_handles_invalid_json(self, patch_claude_finder):
        """Test conversation handles non-JSON response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not valid json")
            ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        assert ready is False
        assert question is not None
        assert drafts is None

    def test_handles_null_values(self, patch_claude_finder):
        """Test handling of null values in response."""
        response = {
            "structured_output": {
                "ready": True,
                "issues": [{"title": None, "description": None, "size": None, "tasks": None}]
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            ready, question, drafts = draft_issue_conversation([{"role": "user", "content": "test"}])

        # Should handle gracefully with defaults
        assert ready is True

    def test_handles_wrong_type_in_array(self, patch_claude_finder):
        """Test handling wrong types in arrays."""
        response = {
            "structured_output": {
                "tasks": "not an array"  # Should be array
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=json.dumps(response))
            issue = Issue(number=1, title="Test", body="Body", labels=[])
            result = breakdown_issue(issue)

        # Should fallback gracefully
        assert len(result) == 1  # Fallback task

    def test_handles_subprocess_error(self, patch_claude_finder):
        """Test handling subprocess errors."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "claude")
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = estimate_issue_size(issue)

        assert result == "M"  # Default fallback

    def test_handles_empty_response(self, patch_claude_finder):
        """Test handling empty response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            issue = Issue(number=1, title="Test", body="", labels=[])
            result = estimate_issue_size(issue)

        assert result == "M"


class TestSchemaDefinitions:
    """Tests verifying schema definitions are valid JSON."""

    def test_size_schema_is_valid_json(self):
        """Test SIZE_SCHEMA is valid JSON."""
        parsed = json.loads(SIZE_SCHEMA)
        assert parsed["type"] == "object"
        assert "size" in parsed["properties"]

    def test_breakdown_schema_is_valid_json(self):
        """Test BREAKDOWN_SCHEMA is valid JSON."""
        parsed = json.loads(BREAKDOWN_SCHEMA)
        assert parsed["type"] == "object"
        assert "tasks" in parsed["properties"]

    def test_conversation_schema_is_valid_json(self):
        """Test CONVERSATION_SCHEMA is valid JSON."""
        parsed = json.loads(CONVERSATION_SCHEMA)
        assert parsed["type"] == "object"
        assert "ready" in parsed["properties"]
        assert "issues" in parsed["properties"]

    def test_groom_schema_is_valid_json(self):
        """Test GROOM_SCHEMA is valid JSON."""
        parsed = json.loads(GROOM_SCHEMA)
        assert parsed["type"] == "object"
        assert "ready" in parsed["properties"]
        assert "refined_description" in parsed["properties"]

    def test_similar_issues_schema_is_valid_json(self):
        """Test SIMILAR_ISSUES_SCHEMA is valid JSON."""
        parsed = json.loads(SIMILAR_ISSUES_SCHEMA)
        assert parsed["type"] == "object"
        assert "similar_issues" in parsed["properties"]

    def test_closing_comment_schema_is_valid_json(self):
        """Test CLOSING_COMMENT_SCHEMA is valid JSON."""
        parsed = json.loads(CLOSING_COMMENT_SCHEMA)
        assert parsed["type"] == "object"
        assert "comment" in parsed["properties"]
