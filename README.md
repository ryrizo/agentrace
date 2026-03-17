# Agentrace

**Observability for Claude Code sessions.**

When your team starts using AI agents seriously — skills, knowledge trees, context
files — you eventually ask: *is any of this actually working?*

Agentrace answers that. It reads Claude Code's local session logs directly (no
setup, no hooks needed) and shows you what context was loaded, how many tokens
it cost, and whether your optimizations are actually reducing cost.

---

## The Problem

When you move a team to AI-assisted workflows, you make bets:

- "This skills library will make agents more consistent."
- "This knowledge tree will reduce how much context we load."
- "These hooks will keep docs up to date automatically."

Right now those are gut feelings. Agentrace makes them measurable.

---

## How It Works

Claude Code stores full session logs at `~/.claude/projects/`. Agentrace
parses them — token counts, cache efficiency, every file read — with no
configuration and no external services.

```
~/.claude/projects/{project}/
    {session-id}.jsonl   ← agentrace reads these
```

---

## Usage

<!-- USAGE:START — auto-updated by agents. Do not edit this block manually. -->

### `agentrace sessions [PROJECT_PATH]`

List recent Claude Code sessions with token counts, file counts, and duration.

```
SESSION                                SLUG                         MODEL                  FILES     TOKENS   MIN
---------------------------------------------------------------------------------------------------------------
e927ea8e-c4a3-45d1-a939-0af5887e8945  (no slug)                    opus-4-6                   9    730,604     1
25c7503a-b036-481c-81fd-39e4a863eaf8  (no slug)                    opus-4-6                  10  3,327,657     4
```

---

### `agentrace show SESSION_ID`

Full detail for a single session: token breakdown (fresh vs cached),
cache hit rate, duration, and every context file loaded.

```
── Session: e927ea8e-c4a3-45d1-a939-0af5887e8945
   Model:    claude-opus-4-6
   Duration: 1.3 min

── Tokens
   Input (fresh):            25
   Cache created:       168,130
   Cache hits:          558,985  (77% of input)
   Output:                3,464
   Total:               730,604

── Context files (9 unique)
   ~/workspace/capacity/AGENTS.md
   ~/workspace/capacity/frontend/src/App.tsx
   ...
```

---

### `agentrace stats [PROJECT_PATH]`

Aggregate stats across all sessions: total tokens, averages, cache hit rate,
and a bar chart of most-loaded context files.

```
── Stats across 9 sessions
   Total tokens:      15,959,967
   Avg per session:    1,773,329
   Avg files read:             8
   Cache hit rate:            84%

── Most-loaded context files
      5x  █████  ~/workspace/capacity/frontend/src/App.tsx
      4x  ████   ~/workspace/capacity/app/api/router.py
      3x  ███    ~/workspace/capacity/AGENTS.md
```

---

### `agentrace compare SESSION_A SESSION_B`

Diff two sessions side by side. Shows token delta, cache efficiency change,
and which context files were added or removed between sessions. This is the
core command for proving that a knowledge tree or AGENTS.md refactor
actually reduced cost.

```
── Compare
   A: e927ea8e  (2026-03-09)   — before AGENTS.md refactor
   B: 25c7503a  (2026-03-09)   — after

── Tokens                         A             B       DELTA
   Total                    730,604     3,327,657  +2,597,053 ✗
   Cache hit rate               77%           92%            ✓

── Context files  (A: 9  B: 10)
   In both (2): AGENTS.md, ProjectList.tsx
   Only in A — removed in B (7): App.tsx, HeatmapCell.tsx ...
   Only in B — added vs A (8): router.py, DATA_MODELS.md ...

── Summary
   B used 2,597,053 more tokens (355% increase)
```

---

### `agentrace watch [PROJECT_PATH]`

Live session monitor. Waits for a new Claude Code session to start, then
tails it in real-time — showing every file loaded, every exec/write/edit,
and a running token count as the session progresses.

Run it in a split terminal while you work in Claude Code.

```
agentrace watch  waiting for a new Claude Code session…
  press Ctrl+C to stop

● Session started  mighty-munching-goose
  id:   e927ea8e
  cwd:  ~/workspace/capacity

  09:14:22  📄 loaded   ~/workspace/capacity/AGENTS.md
  09:14:23  📄 loaded   ~/workspace/capacity/app/api/router.py
  09:14:25  ◈ tokens    total 42k  cache 84%  out 1.2k
  09:14:28  ✏  edit     ~/workspace/capacity/app/api/router.py
  09:14:30  ⚡ exec      cd frontend && npm run build
  09:14:45  ◈ tokens    total 89k  cache 91%  out 3.1k

── Session ended  (2.1 min)
   Tokens:     89k  (cache 91%)
   Files read: 4
```

<!-- USAGE:END -->

---

## Install

```bash
git clone <repo>
cd agentrace
uv venv && uv pip install -e .
agentrace sessions
```

---

## Status

Working local CLI. All commands read directly from `~/.claude/projects/` —
no configuration or external services required.

See `docs/VISION.md` for roadmap and data model.
