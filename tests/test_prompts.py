"""Tests for prompt construction in AI module."""

import json
import pytest
from unittest.mock import patch, MagicMock

from tshirts.github_client import Issue
from tshirts.ai import (
    estimate_issue_size,
    breakdown_issue,
    draft_issue_conversation,
    groom_issue_conversation,
    find_similar_issues,
    generate_closing_comment,
    DraftIssue,
)


@pytest.fixture
def capture_prompt():
    """Fixture to capture the prompt passed to _call_claude."""
    captured = {"prompt": None, "schema": None}

    def mock_call(prompt, schema=None):
        captured["prompt"] = prompt
        captured["schema"] = schema
        return json.dumps({"structured_output": {}})

    with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
        with patch("tshirts.ai._call_claude", side_effect=mock_call):
            yield captured


class TestEstimatePromptConstruction:
    """Tests for estimate_issue_size prompt construction."""

    def test_includes_issue_number(self, capture_prompt):
        """Test that prompt includes issue number."""
        issue = Issue(number=42, title="Test", body="Body", labels=[])
        estimate_issue_size(issue)

        assert "#42" in capture_prompt["prompt"]

    def test_includes_issue_title(self, capture_prompt):
        """Test that prompt includes issue title."""
        issue = Issue(number=1, title="Fix authentication bug", body="", labels=[])
        estimate_issue_size(issue)

        assert "Fix authentication bug" in capture_prompt["prompt"]

    def test_includes_issue_body(self, capture_prompt):
        """Test that prompt includes issue body/description."""
        issue = Issue(number=1, title="Test", body="Detailed description here", labels=[])
        estimate_issue_size(issue)

        assert "Detailed description here" in capture_prompt["prompt"]

    def test_includes_size_guide(self, capture_prompt):
        """Test that prompt includes t-shirt size guide."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        estimate_issue_size(issue)

        prompt = capture_prompt["prompt"]
        assert "XS" in prompt
        assert "S" in prompt
        assert "M" in prompt
        assert "L" in prompt
        assert "XL" in prompt

    def test_handles_empty_body(self, capture_prompt):
        """Test prompt construction with empty body."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        estimate_issue_size(issue)

        # Should not crash, prompt should still be valid
        assert "#1" in capture_prompt["prompt"]

    def test_handles_special_characters_in_title(self, capture_prompt):
        """Test prompt with special characters in title."""
        issue = Issue(number=1, title='Fix "quotes" & <brackets>', body="", labels=[])
        estimate_issue_size(issue)

        assert '"quotes"' in capture_prompt["prompt"]
        assert "&" in capture_prompt["prompt"]
        assert "<brackets>" in capture_prompt["prompt"]

    def test_handles_multiline_body(self, capture_prompt):
        """Test prompt with multiline body."""
        body = """Line 1
        Line 2

        Line 4 after blank"""
        issue = Issue(number=1, title="Test", body=body, labels=[])
        estimate_issue_size(issue)

        assert "Line 1" in capture_prompt["prompt"]
        assert "Line 4 after blank" in capture_prompt["prompt"]


class TestBreakdownPromptConstruction:
    """Tests for breakdown_issue prompt construction."""

    def test_includes_issue_context(self, capture_prompt):
        """Test that breakdown prompt includes full issue context."""
        issue = Issue(number=99, title="Big Feature", body="Implement X", labels=[])
        breakdown_issue(issue)

        prompt = capture_prompt["prompt"]
        assert "Issue #99" in prompt
        assert "Big Feature" in prompt
        assert "Implement X" in prompt

    def test_includes_subtask_instructions(self, capture_prompt):
        """Test that prompt includes subtask creation instructions."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        breakdown_issue(issue)

        prompt = capture_prompt["prompt"]
        assert "sub-task" in prompt.lower() or "subtask" in prompt.lower()
        assert "3-7" in prompt  # Number of subtasks guidance

    def test_includes_size_criteria(self, capture_prompt):
        """Test that prompt includes size estimation criteria."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        breakdown_issue(issue)

        prompt = capture_prompt["prompt"]
        assert "XS" in prompt
        assert "M" in prompt

    def test_handles_long_body(self, capture_prompt):
        """Test prompt with very long body."""
        body = "x" * 5000  # Very long description
        issue = Issue(number=1, title="Test", body=body, labels=[])
        breakdown_issue(issue)

        # Should include the full body
        assert body in capture_prompt["prompt"]


class TestDraftIssueConversationPromptConstruction:
    """Tests for draft_issue_conversation prompt construction."""

    def test_includes_conversation_history(self, capture_prompt):
        """Test that prompt includes full conversation history."""
        conversation = [
            {"role": "user", "content": "I want to add dark mode"},
            {"role": "assistant", "content": "What framework?"},
            {"role": "user", "content": "React"},
        ]
        draft_issue_conversation(conversation)

        prompt = capture_prompt["prompt"]
        assert "dark mode" in prompt
        assert "framework" in prompt.lower()
        assert "React" in prompt

    def test_includes_user_and_assistant_labels(self, capture_prompt):
        """Test that conversation history labels roles correctly."""
        conversation = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Response"},
        ]
        draft_issue_conversation(conversation)

        prompt = capture_prompt["prompt"]
        assert "User:" in prompt or "user" in prompt.lower()

    def test_includes_multi_issue_instructions(self, capture_prompt):
        """Test that prompt mentions creating separate issues."""
        conversation = [{"role": "user", "content": "test"}]
        draft_issue_conversation(conversation)

        prompt = capture_prompt["prompt"]
        assert "separate" in prompt.lower() or "multiple" in prompt.lower()

    def test_handles_empty_conversation(self, capture_prompt):
        """Test prompt with empty conversation."""
        draft_issue_conversation([])

        # Should not crash
        assert capture_prompt["prompt"] is not None

    def test_handles_special_characters_in_messages(self, capture_prompt):
        """Test conversation with special characters."""
        conversation = [
            {"role": "user", "content": "Fix the <div> & \"quoted\" issue"}
        ]
        draft_issue_conversation(conversation)

        prompt = capture_prompt["prompt"]
        assert "<div>" in prompt
        assert "&" in prompt
        assert '"quoted"' in prompt


class TestGroomIssueConversationPromptConstruction:
    """Tests for groom_issue_conversation prompt construction."""

    def test_includes_issue_details(self, capture_prompt):
        """Test that groom prompt includes full issue details."""
        issue = Issue(number=55, title="Refactor API", body="Current API is messy", labels=["size: L"])
        groom_issue_conversation(issue, [])

        prompt = capture_prompt["prompt"]
        assert "Issue #55" in prompt
        assert "Refactor API" in prompt
        assert "Current API is messy" in prompt

    def test_includes_current_size(self, capture_prompt):
        """Test that prompt includes current size from labels."""
        issue = Issue(number=1, title="Test", body="", labels=["size: XL", "bug"])
        groom_issue_conversation(issue, [])

        prompt = capture_prompt["prompt"]
        assert "XL" in prompt

    def test_includes_conversation_history(self, capture_prompt):
        """Test that groom prompt includes conversation history."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        conversation = [
            {"role": "assistant", "content": "What is the goal?"},
            {"role": "user", "content": "Better performance"},
        ]
        groom_issue_conversation(issue, conversation)

        prompt = capture_prompt["prompt"]
        assert "goal" in prompt.lower()
        assert "Better performance" in prompt

    def test_includes_refinement_guidance(self, capture_prompt):
        """Test that prompt includes refinement criteria."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        groom_issue_conversation(issue, [])

        prompt = capture_prompt["prompt"]
        assert "clarif" in prompt.lower()  # clarification/clarify
        assert "requirement" in prompt.lower() or "criteria" in prompt.lower()


class TestFindSimilarIssuesPromptConstruction:
    """Tests for find_similar_issues prompt construction."""

    def test_includes_draft_details(self, capture_prompt):
        """Test that prompt includes draft issue details."""
        draft = DraftIssue(title="Add caching", description="Cache API responses", size="M", tasks=[])
        existing = [Issue(number=1, title="Other", body="", labels=[])]
        find_similar_issues(draft, existing)

        prompt = capture_prompt["prompt"]
        assert "Add caching" in prompt
        assert "Cache API responses" in prompt

    def test_includes_existing_issues(self, capture_prompt):
        """Test that prompt includes existing issues."""
        draft = DraftIssue(title="New", description="New feature", size="S", tasks=[])
        existing = [
            Issue(number=10, title="Old Feature", body="Description of old", labels=[]),
            Issue(number=20, title="Another", body="Another desc", labels=[]),
        ]
        find_similar_issues(draft, existing)

        prompt = capture_prompt["prompt"]
        assert "#10" in prompt
        assert "Old Feature" in prompt
        assert "#20" in prompt

    def test_includes_relationship_definitions(self, capture_prompt):
        """Test that prompt defines relationship types."""
        draft = DraftIssue(title="Test", description="", size="S", tasks=[])
        existing = [Issue(number=1, title="X", body="", labels=[])]
        find_similar_issues(draft, existing)

        prompt = capture_prompt["prompt"]
        assert "duplicate" in prompt
        assert "subtask" in prompt
        assert "related" in prompt

    def test_truncates_long_descriptions(self, capture_prompt):
        """Test that long issue descriptions are truncated."""
        draft = DraftIssue(title="Test", description="", size="S", tasks=[])
        long_body = "x" * 500
        existing = [Issue(number=1, title="Long", body=long_body, labels=[])]
        find_similar_issues(draft, existing)

        # Should truncate to 200 chars
        prompt = capture_prompt["prompt"]
        assert "x" * 200 in prompt
        assert "x" * 500 not in prompt

    def test_limits_number_of_existing_issues(self, capture_prompt):
        """Test that existing issues are limited to 50."""
        draft = DraftIssue(title="Test", description="", size="S", tasks=[])
        existing = [Issue(number=i, title=f"Issue {i}", body="", labels=[]) for i in range(100)]
        find_similar_issues(draft, existing)

        prompt = capture_prompt["prompt"]
        assert "#49" in prompt  # 50th issue (0-indexed)
        assert "#99" not in prompt  # 100th issue should be excluded


class TestGenerateClosingCommentPromptConstruction:
    """Tests for generate_closing_comment prompt construction."""

    def test_includes_issue_details(self, capture_prompt):
        """Test that prompt includes issue being closed."""
        issue = Issue(number=77, title="Fix bug", body="Bug description", labels=[])
        generate_closing_comment(issue, [])

        prompt = capture_prompt["prompt"]
        assert "Issue #77" in prompt
        assert "Fix bug" in prompt

    def test_includes_sub_issues_when_present(self, capture_prompt):
        """Test that prompt includes completed sub-issues."""
        issue = Issue(number=1, title="Parent", body="", labels=[])
        sub_issues = [
            Issue(number=2, title="Sub task 1", body="", labels=[]),
            Issue(number=3, title="Sub task 2", body="", labels=[]),
        ]
        generate_closing_comment(issue, sub_issues)

        prompt = capture_prompt["prompt"]
        assert "#2" in prompt
        assert "Sub task 1" in prompt
        assert "#3" in prompt

    def test_includes_closure_reason_when_provided(self, capture_prompt):
        """Test that prompt includes closure reason."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        generate_closing_comment(issue, [], reason="Completed manually")

        prompt = capture_prompt["prompt"]
        assert "Completed manually" in prompt

    def test_truncates_long_body(self, capture_prompt):
        """Test that very long issue body is truncated."""
        long_body = "y" * 1000
        issue = Issue(number=1, title="Test", body=long_body, labels=[])
        generate_closing_comment(issue, [])

        prompt = capture_prompt["prompt"]
        # Should truncate to 500 chars
        assert "y" * 500 in prompt
        assert "y" * 1000 not in prompt

    def test_handles_none_body(self, capture_prompt):
        """Test prompt when issue body is empty/None."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        generate_closing_comment(issue, [])

        # Should handle gracefully with fallback text
        assert "(no description)" in capture_prompt["prompt"] or "Test" in capture_prompt["prompt"]


class TestPromptEdgeCases:
    """Edge case tests for prompt construction."""

    def test_unicode_characters(self, capture_prompt):
        """Test prompts handle unicode properly."""
        issue = Issue(number=1, title="Fix emoji 🐛 bug", body="日本語テスト", labels=[])
        estimate_issue_size(issue)

        prompt = capture_prompt["prompt"]
        assert "🐛" in prompt
        assert "日本語" in prompt

    def test_newlines_and_tabs(self, capture_prompt):
        """Test prompts preserve newlines and tabs."""
        issue = Issue(number=1, title="Test", body="Line1\n\tIndented\nLine3", labels=[])
        estimate_issue_size(issue)

        prompt = capture_prompt["prompt"]
        assert "Line1" in prompt
        assert "Indented" in prompt
        assert "Line3" in prompt

    def test_markdown_in_body(self, capture_prompt):
        """Test prompts handle markdown content."""
        body = """## Heading

- Bullet 1
- Bullet 2

```python
def test():
    pass
```"""
        issue = Issue(number=1, title="Test", body=body, labels=[])
        breakdown_issue(issue)

        prompt = capture_prompt["prompt"]
        assert "## Heading" in prompt
        assert "- Bullet" in prompt
        assert "```python" in prompt

    def test_very_long_title(self, capture_prompt):
        """Test prompt with very long title."""
        long_title = "A" * 500
        issue = Issue(number=1, title=long_title, body="", labels=[])
        estimate_issue_size(issue)

        # Should include full title
        assert long_title in capture_prompt["prompt"]

    def test_issue_with_no_labels(self, capture_prompt):
        """Test groom prompt when issue has no labels."""
        issue = Issue(number=1, title="Test", body="", labels=[])
        groom_issue_conversation(issue, [])

        # Should handle gracefully, show Unknown size
        prompt = capture_prompt["prompt"]
        assert "Unknown" in prompt or "Issue #1" in prompt
