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
