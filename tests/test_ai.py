"""Tests for the AI module."""

import json
import pytest
from unittest.mock import patch, MagicMock

from tshirts.ai import (
    estimate_issue_size,
    breakdown_issue,
    find_similar_issues,
    generate_closing_comment,
)


class TestEstimateIssueSize:
    """Tests for estimate_issue_size function."""

    def test_returns_valid_size(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that estimate returns a valid t-shirt size."""
        with patch("subprocess.run", return_value=mock_claude_response({"size": "M"})):
            result = estimate_issue_size(sample_issue)
            assert result in ["XS", "S", "M", "L", "XL"]

    def test_defaults_to_medium_on_error(self, sample_issue, mock_claude_error, patch_claude_finder):
        """Test that estimate defaults to M on error."""
        with patch("subprocess.run", return_value=mock_claude_error()):
            result = estimate_issue_size(sample_issue)
            assert result == "M"

    def test_defaults_to_medium_on_invalid_json(self, sample_issue, mock_claude_invalid_json, patch_claude_finder):
        """Test that estimate defaults to M on invalid JSON."""
        with patch("subprocess.run", return_value=mock_claude_invalid_json):
            result = estimate_issue_size(sample_issue)
            assert result == "M"


class TestBreakdownIssue:
    """Tests for breakdown_issue function."""

    def test_returns_list_of_subtasks(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that breakdown returns a list of SubTask objects."""
        tasks_data = {
            "tasks": [
                {"title": "Task 1", "description": "Do thing 1", "size": "S"},
                {"title": "Task 2", "description": "Do thing 2", "size": "M"},
            ]
        }
        with patch("subprocess.run", return_value=mock_claude_response(tasks_data)):
            result = breakdown_issue(sample_issue)
            assert len(result) == 2
            assert result[0].title == "Task 1"
            assert result[1].size == "M"

    def test_returns_fallback_on_error(self, sample_issue, mock_claude_error, patch_claude_finder):
        """Test that breakdown returns fallback task on error."""
        with patch("subprocess.run", return_value=mock_claude_error()):
            result = breakdown_issue(sample_issue)
            assert len(result) == 1
            assert "Test Issue" in result[0].title


class TestFindSimilarIssues:
    """Tests for find_similar_issues function."""

    def test_returns_empty_list_when_no_existing_issues(self, sample_draft_issue):
        """Test that find_similar_issues returns empty list with no existing issues."""
        result = find_similar_issues(sample_draft_issue, [])
        assert result == []

    def test_finds_similar_issues(self, sample_draft_issue, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that find_similar_issues returns matches."""
        similar_data = {
            "similar_issues": [
                {"issue_number": 42, "relationship": "related", "reasoning": "Similar topic"}
            ]
        }
        with patch("subprocess.run", return_value=mock_claude_response(similar_data)):
            result = find_similar_issues(sample_draft_issue, [sample_issue])
            assert len(result) == 1
            assert result[0].issue_number == 42
            assert result[0].relationship == "related"


class TestGenerateClosingComment:
    """Tests for generate_closing_comment function."""

    def test_generates_comment(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that generate_closing_comment returns a comment string."""
        with patch("subprocess.run", return_value=mock_claude_response({"comment": "Issue resolved."})):
            result = generate_closing_comment(sample_issue, [], reason="Fixed")
            assert result == "Issue resolved."

    def test_returns_fallback_on_error(self, sample_issue, mock_claude_error, patch_claude_finder):
        """Test that generate_closing_comment returns fallback on error."""
        with patch("subprocess.run", return_value=mock_claude_error()):
            result = generate_closing_comment(sample_issue, [], reason="Done")
            assert "closed" in result.lower()


class TestDraftIssueConversation:
    """Tests for draft_issue_conversation function."""

    def test_returns_question_when_not_ready(self, mock_claude_response, patch_claude_finder):
        """Test that conversation returns a question when more info needed."""
        from tshirts.ai import draft_issue_conversation
        
        response_data = {
            "ready": False,
            "question": "What problem does this solve?"
        }
        with patch("subprocess.run", return_value=mock_claude_response(response_data)):
            ready, question, drafts = draft_issue_conversation([
                {"role": "user", "content": "I want to add a feature"}
            ])
            assert ready is False
            assert question == "What problem does this solve?"
            assert drafts is None

    def test_returns_drafts_when_ready(self, mock_claude_response, patch_claude_finder):
        """Test that conversation returns draft issues when ready."""
        from tshirts.ai import draft_issue_conversation
        
        response_data = {
            "ready": True,
            "issues": [
                {"title": "Add feature X", "description": "Implement X", "size": "M", "tasks": ["Task 1"]}
            ]
        }
        with patch("subprocess.run", return_value=mock_claude_response(response_data)):
            ready, question, drafts = draft_issue_conversation([
                {"role": "user", "content": "I want to add feature X"}
            ])
            assert ready is True
            assert question is None
            assert len(drafts) == 1
            assert drafts[0].title == "Add feature X"

    def test_handles_error_gracefully(self, mock_claude_error, patch_claude_finder):
        """Test that conversation handles errors gracefully."""
        from tshirts.ai import draft_issue_conversation
        
        with patch("subprocess.run", return_value=mock_claude_error()):
            ready, question, drafts = draft_issue_conversation([
                {"role": "user", "content": "test"}
            ])
            assert ready is False
            assert question is not None
            assert drafts is None


class TestGroomIssueConversation:
    """Tests for groom_issue_conversation function."""

    def test_returns_question_when_not_ready(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that groom returns a question when clarification needed."""
        from tshirts.ai import groom_issue_conversation
        
        response_data = {
            "ready": False,
            "question": "What is the acceptance criteria?",
            "suggestions": []
        }
        with patch("subprocess.run", return_value=mock_claude_response(response_data)):
            ready, question, refined, suggestions = groom_issue_conversation(sample_issue, [])
            assert ready is False
            assert question == "What is the acceptance criteria?"
            assert refined is None

    def test_returns_refined_description_when_ready(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that groom returns refined description when ready."""
        from tshirts.ai import groom_issue_conversation
        
        response_data = {
            "ready": True,
            "refined_description": "Improved description with clear requirements.",
            "suggestions": ["Consider breaking into smaller tasks"]
        }
        with patch("subprocess.run", return_value=mock_claude_response(response_data)):
            ready, question, refined, suggestions = groom_issue_conversation(sample_issue, [])
            assert ready is True
            assert question is None
            assert refined == "Improved description with clear requirements."
            assert len(suggestions) == 1


class TestEstimateIssueSizeEdgeCases:
    """Additional edge case tests for estimate_issue_size."""

    def test_handles_all_valid_sizes(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that all valid sizes are accepted."""
        for size in ["XS", "S", "M", "L", "XL"]:
            with patch("subprocess.run", return_value=mock_claude_response({"size": size})):
                result = estimate_issue_size(sample_issue)
                assert result == size

    def test_handles_missing_size_field(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test fallback when size field is missing."""
        with patch("subprocess.run", return_value=mock_claude_response({})):
            result = estimate_issue_size(sample_issue)
            assert result == "M"


class TestBreakdownIssueEdgeCases:
    """Additional edge case tests for breakdown_issue."""

    def test_handles_empty_tasks_array(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test handling of empty tasks array."""
        with patch("subprocess.run", return_value=mock_claude_response({"tasks": []})):
            result = breakdown_issue(sample_issue)
            assert isinstance(result, list)

    def test_normalizes_size_to_uppercase(self, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that size is normalized to uppercase."""
        tasks_data = {
            "tasks": [
                {"title": "Task", "description": "Desc", "size": "xs"}
            ]
        }
        with patch("subprocess.run", return_value=mock_claude_response(tasks_data)):
            result = breakdown_issue(sample_issue)
            assert result[0].size == "XS"


class TestFindSimilarIssuesEdgeCases:
    """Additional edge case tests for find_similar_issues."""

    def test_filters_out_distinct_issues(self, sample_draft_issue, sample_issue, mock_claude_response, patch_claude_finder):
        """Test that distinct issues are filtered out."""
        similar_data = {
            "similar_issues": [
                {"issue_number": 42, "relationship": "distinct", "reasoning": "Not related"}
            ]
        }
        with patch("subprocess.run", return_value=mock_claude_response(similar_data)):
            result = find_similar_issues(sample_draft_issue, [sample_issue])
            assert len(result) == 0

    def test_handles_duplicate_relationship(self, sample_draft_issue, sample_issue, mock_claude_response, patch_claude_finder):
        """Test handling of duplicate relationship."""
        similar_data = {
            "similar_issues": [
                {"issue_number": 42, "relationship": "duplicate", "reasoning": "Same issue"}
            ]
        }
        with patch("subprocess.run", return_value=mock_claude_response(similar_data)):
            result = find_similar_issues(sample_draft_issue, [sample_issue])
            assert len(result) == 1
            assert result[0].relationship == "duplicate"


class TestGenerateClosingCommentEdgeCases:
    """Additional edge case tests for generate_closing_comment."""

    def test_includes_sub_issues_in_fallback(self, sample_issue, mock_claude_error, patch_claude_finder):
        """Test that fallback mentions sub-issues count."""
        from tshirts.github_client import Issue
        sub_issues = [
            Issue(number=1, title="Sub 1", body="", labels=[]),
            Issue(number=2, title="Sub 2", body="", labels=[])
        ]
        with patch("subprocess.run", return_value=mock_claude_error()):
            result = generate_closing_comment(sample_issue, sub_issues)
            assert "2" in result
