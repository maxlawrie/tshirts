# tshirts

A CLI tool for breaking down GitHub issues into smaller pieces using AI.

## Commands

- `tshirts estimate` - Assigns t-shirt size labels (XS, S, M, L, XL) to issues without them
- `tshirts breakdown <issue>` - Breaks an issue into smaller sub-tasks
- `tshirts breakdown <issue> --create` - Creates sub-issues automatically
- `tshirts new` - Interactive AI-assisted issue creation with conversational flow

## Repo Detection

1. Auto-detects from git remote if in a repo
2. Shows interactive picker otherwise
3. Can override with `--repo owner/name` or `TSHIRTS_REPO` env var

## Architecture

```
src/tshirts/
├── cli.py          # Click CLI commands
├── github_client.py # PyGithub integration, label management
└── ai.py           # Claude CLI integration with JSON schemas
```

## Key Implementation Details

- Uses Claude CLI (not SDK) to work with Claude Max subscription
- Prompts passed via stdin to handle multi-line content
- Structured output via `--json-schema` for reliable parsing
- Size labels: `size: XS`, `size: S`, `size: M`, `size: L`, `size: XL`

## Development

```bash
pip install -e .
GITHUB_TOKEN=$(gh auth token) tshirts estimate
```

## Testing

Test against the tshirts repo itself or TerminalDX12:
```bash
tshirts --repo maxlawrie/TerminalDX12 estimate
tshirts --repo maxlawrie/TerminalDX12 breakdown 11
```
