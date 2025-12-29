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
