# tshirts

A CLI tool for breaking down GitHub issues into smaller pieces using AI.

## Installation

```bash
pip install -e .
```

## Setup

### Requirements

- **Claude Code CLI** - Must be installed and authenticated (`claude` command available)
- **GitHub Token** - For accessing GitHub issues

```bash
# Authenticate Claude Code (works with Claude Max subscription)
claude login

# Set GitHub token (or use `gh auth token` if you have gh CLI)
export GITHUB_TOKEN="your-github-token"
```

## Usage

### Estimate issue sizes

Assign t-shirt size labels (XS, S, M, L, XL) to all open issues that don't have one:

```bash
tshirts estimate
```

### Break down an issue

Break a large issue into smaller, actionable tasks:

```bash
tshirts breakdown 42
```

To automatically create sub-issues:

```bash
tshirts breakdown 42 --create
```

### Repo selection

tshirts automatically detects which repo to use:

1. **From git** - If you're in a git repo with a GitHub remote, it uses that
2. **Interactive** - Otherwise, it shows your repos and lets you pick one
3. **Explicit** - You can always specify with `--repo owner/name`

```bash
# Explicit repo
tshirts --repo owner/repo estimate

# Or set via environment variable
export TSHIRTS_REPO="owner/repo"
tshirts estimate
```

## Size Guide

| Size | Time Estimate | Examples |
|------|---------------|----------|
| XS   | <30 min       | Typo fix, config change |
| S    | 1-2 hours     | Simple bug fix, small feature |
| M    | Half day - 1 day | Moderate feature, multiple files |
| L    | 2-3 days      | Significant feature, refactoring |
| XL   | 1+ week       | Major feature, needs breakdown |

## MCP Server

tshirts can also run as an MCP (Model Context Protocol) server, allowing LLM clients like Claude Desktop to use its functionality.

### Running the server

```bash
tshirts-mcp
```

### Claude Desktop configuration

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tshirts": {
      "command": "python",
      "args": ["-m", "tshirts.mcp"],
      "env": {
        "GITHUB_TOKEN": "your-github-token"
      }
    }
  }
}
```

### Available tools

| Tool | Description |
|------|-------------|
| `estimate_issue` | Estimate t-shirt size for an issue |
| `breakdown_issue` | Break issue into subtasks |
| `draft_issue` | Generate issue draft from description |
| `refine_issue` | Suggest improvements to an issue |
| `find_similar_issues` | Check for duplicate/related issues |
| `generate_closing_comment` | Generate AI closing comment |
| `apply_size_label` | Apply size label to issue |
| `create_issue` | Create a new issue |
| `create_subtasks` | Create subtasks linked to parent |
| `update_issue_body` | Update issue description |
| `close_issue` | Close issue with optional comment |

### Available resources

| Resource | Description |
|----------|-------------|
| `github://{repo}/issues` | List open issues |
| `github://{repo}/issues/{number}` | Get specific issue |
| `github://{repo}/issues/unestimated` | Issues without size labels |
| `github://{repo}/issues/groomable` | Issues needing refinement |
| `github://repos` | List your repositories |

## Development

### Running tests

```bash
# Install with test dependencies
pip install -e ".[test]"

# Run all tests
pytest

# Run with coverage
pytest --cov=tshirts --cov-report=term-missing
```
