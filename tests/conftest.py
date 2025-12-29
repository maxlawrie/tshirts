"""Shared pytest fixtures for tshirts tests."""

import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_claude_response():
    """Factory fixture for mocking Claude CLI responses."""
    def _mock_response(structured_output: dict, returncode: int = 0):
        """Create a mock subprocess result with structured output."""
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = json.dumps({"structured_output": structured_output})
        mock_result.stderr = ""
        return mock_result
    return _mock_response


@pytest.fixture
def mock_claude_error():
    """Factory fixture for mocking Claude CLI errors."""
    def _mock_error(error_msg: str = "Claude CLI error", returncode: int = 1):
        """Create a mock subprocess result with error."""
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = ""
        mock_result.stderr = error_msg
        return mock_result
    return _mock_error


@pytest.fixture
def mock_claude_invalid_json():
    """Fixture for mocking invalid JSON response from Claude."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "This is not valid JSON"
    mock_result.stderr = ""
    return mock_result


@pytest.fixture
def patch_subprocess_run():
    """Context manager fixture for patching subprocess.run."""
    with patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def patch_claude_finder():
    """Patch the claude CLI finder to return a fake path."""
    with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
        yield


@pytest.fixture
def sample_issue():
    """Create a sample Issue object for testing."""
    from tshirts.github_client import Issue
    return Issue(
        number=42,
        title="Test Issue",
        body="This is a test issue description.",
        labels=["size: M", "bug"]
    )


@pytest.fixture
def sample_draft_issue():
    """Create a sample DraftIssue object for testing."""
    from tshirts.ai import DraftIssue
    return DraftIssue(
        title="New Feature",
        description="Implement a new feature",
        size="M",
        tasks=["Task 1", "Task 2"]
    )
