"""Tests for stdin passing and multi-line content handling."""

import json
import pytest
from unittest.mock import patch, MagicMock, call

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
)


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run and capture calls."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=json.dumps({"structured_output": {}}))
        yield mock_run


@pytest.fixture
def patch_claude_finder():
    """Patch the claude CLI finder."""
    with patch("tshirts.ai._find_claude", return_value="/usr/bin/claude"):
        yield


class TestStdinPassing:
    """Tests verifying prompts are passed via stdin."""

    def test_prompt_passed_via_stdin_input(self, mock_subprocess, patch_claude_finder):
        """Test that prompt is passed via stdin input parameter."""
        _call_claude("test prompt", schema=None)

        call_kwargs = mock_subprocess.call_args[1]
        assert "input" in call_kwargs
        assert call_kwargs["input"] == "test prompt"

    def test_prompt_not_in_command_args(self, mock_subprocess, patch_claude_finder):
        """Test that prompt content is NOT in command line args."""
        prompt = "This is my secret prompt content"
        _call_claude(prompt, schema=None)

        cmd = mock_subprocess.call_args[0][0]
        # The prompt should not appear in the command list
        assert prompt not in cmd
        # But it should be in the input
        assert mock_subprocess.call_args[1]["input"] == prompt

    def test_capture_output_enabled(self, mock_subprocess, patch_claude_finder):
        """Test that capture_output is enabled for subprocess."""
        _call_claude("test", schema=None)

        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs.get("capture_output") is True

    def test_text_mode_enabled(self, mock_subprocess, patch_claude_finder):
        """Test that text mode is enabled for subprocess."""
        _call_claude("test", schema=None)

        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs.get("text") is True


class TestMultiLineContent:
    """Tests for multi-line content handling."""

    def test_handles_simple_newlines(self, mock_subprocess, patch_claude_finder):
        """Test handling of simple newline characters."""
        prompt = "Line 1\nLine 2\nLine 3"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "Line 1\nLine 2\nLine 3" == passed_input

    def test_handles_crlf_newlines(self, mock_subprocess, patch_claude_finder):
        """Test handling of Windows-style CRLF newlines."""
        prompt = "Line 1\r\nLine 2\r\nLine 3"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "Line 1\r\nLine 2\r\nLine 3" == passed_input

    def test_handles_mixed_newlines(self, mock_subprocess, patch_claude_finder):
        """Test handling of mixed newline styles."""
        prompt = "Line 1\nLine 2\r\nLine 3\rLine 4"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert prompt == passed_input

    def test_handles_multiple_blank_lines(self, mock_subprocess, patch_claude_finder):
        """Test handling of multiple consecutive blank lines."""
        prompt = "Paragraph 1\n\n\n\nParagraph 2"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "\n\n\n\n" in passed_input

    def test_preserves_leading_trailing_newlines(self, mock_subprocess, patch_claude_finder):
        """Test that leading and trailing newlines are preserved."""
        prompt = "\n\nContent\n\n"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert passed_input.startswith("\n\n")
        assert passed_input.endswith("\n\n")

    def test_multiline_issue_body(self, mock_subprocess, patch_claude_finder):
        """Test that multi-line issue body is passed correctly."""
        body = """## Description
This is a detailed description.

## Steps to Reproduce
1. First step
2. Second step
3. Third step

## Expected Behavior
It should work."""

        issue = Issue(number=1, title="Bug Report", body=body, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "## Description" in passed_input
        assert "## Steps to Reproduce" in passed_input
        assert "1. First step" in passed_input


class TestSpecialCharacters:
    """Tests for special character handling."""

    def test_handles_quotes(self, mock_subprocess, patch_claude_finder):
        """Test handling of single and double quotes."""
        prompt = 'He said "Hello" and she said \'Hi\''
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert '"Hello"' in passed_input
        assert "'Hi'" in passed_input

    def test_handles_backslashes(self, mock_subprocess, patch_claude_finder):
        """Test handling of backslash characters."""
        prompt = "Path: C:\\Users\\test\\file.txt"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "C:\\Users\\test\\file.txt" in passed_input

    def test_handles_shell_metacharacters(self, mock_subprocess, patch_claude_finder):
        """Test handling of shell metacharacters."""
        prompt = "Run: echo $HOME && ls | grep foo > output.txt"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "$HOME" in passed_input
        assert "&&" in passed_input
        assert "|" in passed_input
        assert ">" in passed_input

    def test_handles_backticks(self, mock_subprocess, patch_claude_finder):
        """Test handling of backticks."""
        prompt = "Use `code` inline and ```blocks```"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "`code`" in passed_input
        assert "```blocks```" in passed_input

    def test_handles_unicode(self, mock_subprocess, patch_claude_finder):
        """Test handling of unicode characters."""
        prompt = "Emoji: 🚀 💻 🐛 | CJK: 你好世界 | Cyrillic: Привет"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "🚀" in passed_input
        assert "你好世界" in passed_input
        assert "Привет" in passed_input

    def test_handles_null_bytes(self, mock_subprocess, patch_claude_finder):
        """Test handling of null byte characters."""
        prompt = "Before\x00After"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert passed_input == "Before\x00After"

    def test_handles_tabs(self, mock_subprocess, patch_claude_finder):
        """Test handling of tab characters."""
        prompt = "Column1\tColumn2\tColumn3"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "\t" in passed_input

    def test_handles_angle_brackets(self, mock_subprocess, patch_claude_finder):
        """Test handling of angle brackets (HTML/XML)."""
        prompt = "<div>Hello</div> <script>alert('xss')</script>"
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "<div>" in passed_input
        assert "</script>" in passed_input

    def test_handles_curly_braces(self, mock_subprocess, patch_claude_finder):
        """Test handling of curly braces (JSON/template syntax)."""
        prompt = '{"key": "value"} and {{template}}'
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert '{"key": "value"}' in passed_input
        assert "{{template}}" in passed_input


class TestCodeBlocks:
    """Tests for code block handling in prompts."""

    def test_handles_python_code_block(self, mock_subprocess, patch_claude_finder):
        """Test handling of Python code blocks."""
        code = '''```python
def hello():
    print("Hello, World!")
    return True

if __name__ == "__main__":
    hello()
```'''
        issue = Issue(number=1, title="Add function", body=code, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "```python" in passed_input
        assert 'def hello():' in passed_input
        assert 'print("Hello, World!")' in passed_input

    def test_handles_javascript_code_block(self, mock_subprocess, patch_claude_finder):
        """Test handling of JavaScript code blocks."""
        code = '''```javascript
const greet = (name) => {
    console.log(`Hello, ${name}!`);
};
```'''
        issue = Issue(number=1, title="JS function", body=code, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "```javascript" in passed_input
        assert "${name}" in passed_input

    def test_handles_shell_code_block(self, mock_subprocess, patch_claude_finder):
        """Test handling of shell command code blocks."""
        code = '''```bash
#!/bin/bash
for i in $(seq 1 10); do
    echo "Number: $i"
done
```'''
        issue = Issue(number=1, title="Shell script", body=code, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "#!/bin/bash" in passed_input
        assert "$(seq 1 10)" in passed_input
        assert '"Number: $i"' in passed_input

    def test_handles_nested_quotes_in_code(self, mock_subprocess, patch_claude_finder):
        """Test handling of nested quotes in code blocks."""
        code = '''```python
message = "She said 'Hello'"
response = 'He replied "Hi"'
```'''
        issue = Issue(number=1, title="Quotes", body=code, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert '''message = "She said 'Hello'"''' in passed_input

    def test_handles_indented_code(self, mock_subprocess, patch_claude_finder):
        """Test that indentation in code is preserved."""
        code = '''```python
class MyClass:
    def method(self):
        if True:
            for i in range(10):
                print(i)
```'''
        issue = Issue(number=1, title="Indented", body=code, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        # Verify indentation is preserved
        assert "    def method" in passed_input
        assert "        if True:" in passed_input
        assert "            for i" in passed_input


class TestLongText:
    """Tests for long text transmission."""

    def test_handles_1kb_prompt(self, mock_subprocess, patch_claude_finder):
        """Test handling of 1KB prompt."""
        prompt = "x" * 1024
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert len(passed_input) == 1024

    def test_handles_10kb_prompt(self, mock_subprocess, patch_claude_finder):
        """Test handling of 10KB prompt."""
        prompt = "y" * (10 * 1024)
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert len(passed_input) == 10 * 1024

    def test_handles_100kb_prompt(self, mock_subprocess, patch_claude_finder):
        """Test handling of 100KB prompt."""
        prompt = "z" * (100 * 1024)
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert len(passed_input) == 100 * 1024

    def test_handles_long_issue_body(self, mock_subprocess, patch_claude_finder):
        """Test that very long issue body is passed completely."""
        long_body = "Description line\n" * 5000  # ~85KB

        issue = Issue(number=1, title="Long Issue", body=long_body, labels=[])
        estimate_issue_size(issue)

        passed_input = mock_subprocess.call_args[1]["input"]
        # The full body should be in the prompt
        assert long_body in passed_input

    def test_handles_many_lines(self, mock_subprocess, patch_claude_finder):
        """Test handling of prompt with many lines."""
        prompt = "\n".join(f"Line {i}" for i in range(10000))
        _call_claude(prompt, schema=None)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "Line 0" in passed_input
        assert "Line 9999" in passed_input


class TestConversationMultiLine:
    """Tests for multi-line content in conversations."""

    def test_conversation_with_multiline_messages(self, mock_subprocess, patch_claude_finder):
        """Test conversation history with multi-line messages."""
        conversation = [
            {"role": "user", "content": "I want to add:\n1. Feature A\n2. Feature B"},
            {"role": "assistant", "content": "Can you explain:\n- What does Feature A do?\n- What does Feature B do?"},
            {"role": "user", "content": "Feature A does X.\nFeature B does Y."},
        ]

        draft_issue_conversation(conversation)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "1. Feature A" in passed_input
        assert "2. Feature B" in passed_input
        assert "- What does Feature A do?" in passed_input

    def test_groom_with_multiline_issue(self, mock_subprocess, patch_claude_finder):
        """Test groom with multi-line issue body."""
        body = """## Problem
The login is broken.

## Expected
User should be able to log in.

## Actual
Error 500 is shown."""

        issue = Issue(number=1, title="Login Bug", body=body, labels=["size: M"])
        groom_issue_conversation(issue, [])

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "## Problem" in passed_input
        assert "## Expected" in passed_input
        assert "Error 500" in passed_input


class TestSimilarIssuesMultiLine:
    """Tests for multi-line content in similar issues."""

    def test_similar_issues_with_multiline_descriptions(self, mock_subprocess, patch_claude_finder):
        """Test similar issues comparison with multi-line descriptions."""
        draft = DraftIssue(
            title="New Feature",
            description="This feature will:\n- Do X\n- Do Y\n- Do Z",
            size="M",
            tasks=[]
        )
        existing = [
            Issue(number=1, title="Related", body="Description\nwith\nmultiple\nlines", labels=[])
        ]

        find_similar_issues(draft, existing)

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "- Do X" in passed_input
        assert "- Do Y" in passed_input


class TestClosingCommentMultiLine:
    """Tests for multi-line content in closing comments."""

    def test_closing_with_multiline_issue(self, mock_subprocess, patch_claude_finder):
        """Test closing comment generation with multi-line issue."""
        issue = Issue(
            number=1,
            title="Complex Bug",
            body="## Description\nBug details here.\n\n## Root Cause\nFound the issue.",
            labels=[]
        )

        generate_closing_comment(issue, [])

        passed_input = mock_subprocess.call_args[1]["input"]
        assert "## Description" in passed_input
        assert "## Root Cause" in passed_input
