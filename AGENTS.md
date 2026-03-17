# AGENTS.md — Agentrace

Entry point for AI coding agents working in this repo. Read this first.

## What This Project Is

Agentrace is a CLI tool for observability of Claude Code sessions.
It parses `~/.claude/projects/` NDJSON files to show token usage,
context files loaded, cache efficiency, and session diffs — with no
configuration, no hooks, and no external services.

## Repository Layout

```
agentrace/
├── README.md                  ← product overview + usage docs (auto-maintained)
├── AGENTS.md                  ← this file
├── pyproject.toml             ← package config + CLI entrypoint
├── .gitignore
├── agentrace/
│   ├── __init__.py
│   ├── parser.py              ← reads + parses ~/.claude/projects/ NDJSON files
│   ├── cost.py                ← session_cost(), estimate_file_tokens(), fmt_cost()
│   ├── display.py             ← ANSI colors, bars, spinners, box/section/rule helpers
│   ├── cli.py                 ← all CLI commands wired together
│   ├── cmd_files.py           ← `agentrace files` — context file cost analysis
│   ├── cmd_recommend.py       ← `agentrace recommend` — context optimization recommendations
│   ├── cmd_diff.py            ← `agentrace diff` — git correlation for context changes
│   ├── cmd_water.py           ← `agentrace water` — water consumption impact report
│   └── watcher.py             ← `agentrace watch` — live session monitor
└── docs/
    └── VISION.md              ← product thinking, data model, roadmap
```

## After Completing a Task

Before committing, check whether your change requires:

| Change type | Update |
|---|---|
| New CLI command added | Update `README.md` Usage section (see hook below) |
| New file added | Update repository layout above |
| New data model or field | Update `docs/VISION.md` data model section |
| New pattern or footgun | Add to Critical Rules below |

## ⚡ README Auto-Update Hook

**This is the post-task hook. Every agent must follow it.**

After adding or modifying any `agentrace` CLI command, update the
`README.md` Usage section between these markers:

```
<!-- USAGE:START — auto-updated by agents. Do not edit this block manually. -->
...
<!-- USAGE:END -->
```

For each command, include:
1. The command signature with args
2. One sentence describing what it does
3. A representative output sample (copy from actual output if possible)

This is how the docs stay current automatically — the agent that adds the
feature also writes the docs for it in the same commit.

## Critical Rules

- Parser lives in `parser.py`, all display/CLI logic in `cli.py`
- Use `_short_path()` for any file path displayed to the user
- `find_sessions()` with no args returns ALL projects; pass a path to scope
- Session IDs only need to be a prefix match (8 chars is enough for `show`/`compare`)
- No external dependencies — keep `dependencies = []` in pyproject.toml
- Use `uv` not `pip`

## Install (dev)

```bash
uv venv && uv pip install -e .
agentrace sessions
```
