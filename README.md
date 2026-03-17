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

### `agentrace projects`

List all Claude Code projects with session counts, total tokens, and last active date.
Auto-detects real project paths from session metadata — no escaped directory names.

```
#    PROJECT                            SESSIONS       TOKENS  LAST ACTIVE
--------------------------------------------------------------------------
1    ~/workspace/capacity                      8        12.7M   2026-03-17
2    ~/workspace/capacity/frontend             2         3.3M   2026-03-08
```

---

### `agentrace sessions [PROJECT]`

List recent Claude Code sessions with token counts, estimated cost, file counts, and duration.

```
#     DATE         SLUG                           MODEL              FILES     TOKENS     COST   MIN
----------------------------------------------------------------------------------------------------
#1    2026-03-17   (ea3a590c)                     opus-4-6               0        42k   $0.163     0
#2    2026-03-09   (e927ea8e)                     opus-4-6               9       731k   $1.729     1
#3    2026-03-09   (25c7503a)                     opus-4-6              10       3.3M   $6.862     4
```

---

### `agentrace show SESSION_ID`

Full detail for a single session: token breakdown (fresh vs cached),
cache hit rate, estimated dollar cost, duration, and every context file loaded.

```
── Session #2
   ID:       e927ea8e-c4a3-45d1-a939-0af5887e8945
   Model:    claude-opus-4-6
   Duration: 1.3 min

── Tokens
   Input (fresh):            25
   Cache created:       168,130
   Cache hits:          558,985  (77% of input)
   Output:                3,464
   Total:               730,604

── Cost
   Estimated:    $1.729
   (opus-4-6 pricing)

── Context files (9 unique)
   ~/workspace/capacity/AGENTS.md
   ~/workspace/capacity/frontend/src/App.tsx
   ...
```

---

### `agentrace stats [PROJECT_PATH]`

Aggregate stats across all sessions: total tokens, averages, cache hit rate,
estimated total cost, and a bar chart of most-loaded context files.

```
── Stats — all projects  (10 sessions)
   Total tokens:        16,001,484
   Avg per session:      1,600,148
   Avg files read:               7
   Cache hit rate:             90%
   Total cost:             $37.731
   Avg cost/session:        $3.773

── Most-loaded context files
      5x  █████  ~/workspace/capacity/frontend/src/App.tsx
      4x  ████   ~/workspace/capacity/app/api/router.py
      3x  ███    ~/workspace/capacity/AGENTS.md
```

---

### `agentrace compare SESSION_A SESSION_B`

Diff two sessions side by side. Shows token delta, estimated cost comparison,
cache efficiency change, and which context files were added or removed between
sessions. This is the core command for proving that a knowledge tree or
AGENTS.md refactor actually reduced cost.

```
── Compare
   A: #2 e927ea8e  (2026-03-09)
   B: #3 25c7503a  (2026-03-09)

── Tokens                         A             B         DELTA
   Total                    730,604     3,327,657  +2,597,053 ✗
   Cache hits               558,985     3,058,116  +2,499,131 ✓
   Output                     3,464        17,206     +13,742 ✗
   Est. cost                 $1.729        $6.862       +$5.133 ✗
   Cache hit rate               77%           92%            ✓

── Context files  (A: 9  B: 10)
   In both (2): AGENTS.md, ProjectList.tsx
   Only in A — removed in B (7): App.tsx, HeatmapCell.tsx ...
   Only in B — added vs A (8): router.py, DATA_MODELS.md ...

── Summary
   B used 2,597,053 more tokens (355% increase)
```

---

### `agentrace files [PROJECT]`

Ranks every context file by total token spend across all sessions. Shows load
count, estimated tokens per load, a proportional bar, and which files no longer
exist on disk (dead references from old refactors).

```
  ╭────────────────────────────────────────────────────────╮
  │  📊  Context File Analysis                             │
  │  10 sessions  ·  75 total loads  ·  49 unique files   │
  ╰────────────────────────────────────────────────────────╯

  Ranked by total token spend

  ~/workspace/capacity/app/api/router.py
  ████████████████████████  27k tokens  (7k/load × 4)

  ~/workspace/capacity/frontend/src/App.tsx
  █████████████░░░░░░░░░░░  18k tokens  (3k/load × 5)

  … and 24 more smaller files

  🗂  5 file(s) no longer on disk: ProjectsView.tsx, CapacityView.tsx …
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

---

### `agentrace tree [PROJECT]`

Detects co-load clusters — groups of files that are consistently loaded together
across sessions. Visualizes your context tree, estimates token savings from
adopting it, and optionally generates a `CLAUDE.md.suggested` skeleton that
encodes the tree as task-specific load instructions.

```
  ╭────────────────────────────────────────────────────────╮
  │  🌳  Context Tree  ~/workspace/capacity                │
  │  10 sessions  ·  49 unique files  ·  3 clusters        │
  ╰────────────────────────────────────────────────────────╯

  📌  Always load  ·  appears in 70%+ of sessions
    AGENTS.md  ~4k tokens

  Cluster 1  Backend API  ·  6/10 sessions
    ██████████████████  router.py    ~7k
    █████████████░░░░░  deps.py      ~2k
    ████████░░░░░░░░░░  calculator.py ~3k

  Cluster 2  Frontend  ·  4/10 sessions
    ██████████████████  App.tsx       ~2k
    ████████████░░░░░░  types/index.ts ~1k

  Current avg files/session  7.5
  Estimated with tree        3.2  (↓ 4.3 fewer)

  ✨ Applying this tree could save ~8k tokens/session

  → Write CLAUDE.md skeleton to CLAUDE.md.suggested? [y/N]
```

---

### `agentrace recommend [PROJECT]`

Analyzes session history and produces actionable recommendations for optimizing
context file usage. Categorizes files into four groups: always load (pin to
CLAUDE.md), load on-demand, consider splitting, and dead weight (no longer on disk).
Shows estimated token savings at the bottom.

```
  ╭────────────────────────────────────────────────────────╮
  │  💡  Context Recommendations                           │
  │  10 sessions  ·  49 unique files  ·  all projects     │
  ╰────────────────────────────────────────────────────────╯

  📌  Add to CLAUDE.md  —  always loaded, small enough to pin
  ~/workspace/capacity/AGENTS.md
  ████████████████████  100% of sessions  ·  3k/load

  🎯  Load on-demand  —  rarely used but costly when loaded
  ~/workspace/capacity/frontend/src/components/ImportProjects.tsx
  ████░░░░░░░░░░░░░░░░  20% of sessions  ·  11k total tokens wasted

  ✂️  Consider splitting  —  large files loaded frequently
  ~/workspace/capacity/app/api/router.py
  ████████░░░░░░░░░░░░  40% of sessions  ·  22k/load  ·  88k total

  🗑  Clean up references  —  files no longer on disk
  ~/workspace/capacity/frontend/src/views/ProjectsView.tsx  ×1 loads

  ──────────────────────────────────────────────────────────

  Estimated token savings  57k tokens
    · 57k from making on-demand files opt-in
```

---

### `agentrace diff [PROJECT]`

Correlates git commits to `AGENTS.md`/`CLAUDE.md` with session token trends.
For each commit that touched context docs, shows before/after average token
usage and whether the change helped reduce cost. Run after each context refactor
to measure impact.

```
  ╭────────────────────────────────────────────────────────╮
  │  🔀  Git Correlation                                   │
  │  AGENTS.md / CLAUDE.md  ·  ~/workspace/capacity       │
  ╰────────────────────────────────────────────────────────╯

  Commits to context docs  →  token impact

  0f9c1a11  2026-03-16  docs: add CLAUDE.md — AI workflow strategy…
    before (9 sessions):  ████████████████  1.8M avg
    after  (1 sessions):  █░░░░░░░░░░░░░░░  42k avg  98% ↓  ✓ helped
    cost change:  -$4.012/session avg

  c7d04ff8  2026-03-08  docs: AGENTS.md + docs/ directory…
    before (6 sessions):  ████████████████  1.7M avg
    after  (4 sessions):  ██████████████░░  1.5M avg  14% ↓  ✓ helped
    cost change:  -$1.178/session avg

  ──────────────────────────────────────────────────────────

  Overall trend across 10 sessions:  27% ↓  (first half avg 1.9M → second half avg 1.3M)
```

---

### `agentrace water [PROJECT]`

Estimates the data center water consumption equivalent of your Claude Code token usage,
based on research showing ~22,500 gallons per 1 billion tokens. Breaks down water impact
by session and by day, with fun real-world comparisons (water bottles, bathtubs, etc.).

```
  ╭─────────────────────────────────────────────────────╮
  │  🌊  Water Impact  all projects                     │
  │  10 sessions  ·  16.0M tokens  ·  est. 360 gallons  │
  ╰─────────────────────────────────────────────────────╯

  Roughly equivalent to

  💧  2,727.5  water bottles
  🛁      7.2  bathtubs
  🌿     30.0  garden hose minutes

  ──────────────────────────────────────────────────────────

  By session  ·  heaviest first

  #6  2026-03-08  ████████████████████   3.5M   79 gal  ≈ 599 bottles
  #3  2026-03-09  ███████████████████░   3.3M   75 gal  ≈ 567 bottles
  #7  2026-03-08  ██████████████░░░░░░   2.4M   55 gal  ≈ 415 bottles
  #1  2026-03-17  ░░░░░░░░░░░░░░░░░░░░    42k 0.93 gal  ≈   7 bottles

  ──────────────────────────────────────────────────────────

  By day

  2026-03-08  ████████████████████  268 gal  (11.9M tokens, 7 sessions)
  2026-03-09  ███████░░░░░░░░░░░░░   91 gal  (4.1M tokens, 2 sessions)
  2026-03-17  ░░░░░░░░░░░░░░░░░░░░ 0.93 gal  (42k tokens, 1 session)

  ──────────────────────────────────────────────────────────

  ⚠  Estimate based on ~22,500 gal / 1B tokens (data center cooling research)
     Actual usage varies by provider, region, and cooling method.
```

<!-- USAGE:END -->

---

## Install

```bash
git clone https://github.com/ryrizo/agentrace.git
cd agentrace
uv tool install --editable .
agentrace sessions
```

Requires [uv](https://docs.astral.sh/uv/). No other dependencies.

### iTerm2 Status Bar (optional)

Shows live token count and cost in your iTerm2 status bar while Claude Code runs.

```bash
bash plugins/install_iterm2.sh
```

See [`plugins/README.md`](plugins/README.md) for setup instructions.

---

## Status

Working local CLI. All commands read directly from `~/.claude/projects/` —
no configuration or external services required.

Zero external dependencies. No API keys. No data leaves your machine.

See `docs/VISION.md` for roadmap.
