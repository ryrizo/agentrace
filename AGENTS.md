# AGENTS.md — Agentrace

Entry point for AI coding agents working in this repo. Read this first.

## What This Project Is

Agentrace is an observability tool for AI agent sessions.
It logs context files loaded, token counts, skills fired, and session outcomes
so teams can prove whether their AI workflow investments (skills, knowledge trees,
hooks) are actually working.

## Project Status

Early stage. Start by reading `docs/VISION.md` for the full product thinking.

## After Completing a Task

Before committing, check whether your change requires:

| Change type | Update |
|---|---|
| New file added | Repository layout below |
| New data model or schema | `docs/VISION.md` data model section |
| New CLI command or API | `docs/VISION.md` interfaces section |
| New pattern discovered | Critical Rules below |

## Repository Layout

```
agentrace/
├── README.md          ← product overview and use cases
├── AGENTS.md          ← this file
├── CLAUDE.md          ← AI workflow strategy (when it exists)
├── .gitignore
└── docs/
    └── VISION.md      ← product thinking, data model, roadmap
```

## Critical Rules

*(none yet — add patterns here as they emerge)*
