# tshirts

A CLI tool for breaking down GitHub issues into smaller pieces using AI.

## Installation

```bash
pip install -e .
```

## Setup

Set the required environment variables:

```bash
export GITHUB_TOKEN="your-github-token"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

## Usage

### Estimate issue sizes

Assign t-shirt size labels (XS, S, M, L, XL) to all open issues that don't have one:

```bash
tshirts --repo owner/repo estimate
```

### Break down an issue

Break a large issue into smaller, actionable tasks:

```bash
tshirts --repo owner/repo breakdown 42
```

To automatically create sub-issues:

```bash
tshirts --repo owner/repo breakdown 42 --create
```

## Size Guide

| Size | Time Estimate | Examples |
|------|---------------|----------|
| XS   | <30 min       | Typo fix, config change |
| S    | 1-2 hours     | Simple bug fix, small feature |
| M    | Half day - 1 day | Moderate feature, multiple files |
| L    | 2-3 days      | Significant feature, refactoring |
| XL   | 1+ week       | Major feature, needs breakdown |
