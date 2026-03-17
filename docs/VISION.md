# VISION.md — Product Thinking

## The Core Insight

AI agents are becoming a layer in how teams work. Like any other layer,
they need observability. You can't improve what you can't measure.

The specific insight that drives Agentrace: when you build a skills library
or a knowledge tree, you're making a structural bet that the AI will behave
better. *Agentrace is how you verify that bet.*

---

## Who It's For

**Primary: Team leads moving their team to AI-assisted workflows.**
They need to justify investment in skills/knowledge infrastructure.
They want to show colleagues that context optimization made a real difference.
They're building a library of agents and want to know which ones get used.

**Secondary: Individual developers.**
"What context did that session actually load?" is a useful debugging question.
Agentrace makes it answerable.

---

## The Measurement Problem

When you optimize an AI workflow, you're typically changing one of:

1. **Context structure** — what files are loaded, how they're organized
2. **Skills** — reusable instruction sets the agent follows
3. **Hooks** — automatic triggers (e.g., "update docs after every commit")

The challenge: the AI's output looks qualitatively similar before and after.
How do you prove the optimized version is actually better?

**Quantitative signals that Agentrace can capture:**
- Token count (in/out) — direct cost proxy
- Number of context files loaded
- Which skills fired
- Session duration
- Lines of code / files changed (outcome proxy)

**Qualitative signals (harder, future work):**
- Did the agent follow the rules?
- Did it need correction?
- Was the output usable on first try?

---

## Data Model (Draft)

### Session
A single agent run — from "agent starts" to "agent finishes."

```
Session {
  id:             string (UUID)
  started_at:     timestamp
  ended_at:       timestamp
  agent:          string  (e.g. "hexed", "claude-code", "codex")
  task:           string  (description of what was asked)
  outcome:        string  (what was produced)

  tokens_in:      int
  tokens_out:     int
  model:          string  (e.g. "claude-sonnet-4-6")

  context_files:  ContextFile[]
  skills_fired:   Skill[]
  tags:           string[]  (e.g. ["capacity-project", "backend", "migration"])
}
```

### ContextFile
One file loaded into context for a session.

```
ContextFile {
  path:           string
  tokens:         int     (approximate — file size proxy)
  loaded_at:      timestamp
  source:         string  (e.g. "AGENTS.md", "skill:coding-agent", "manual")
}
```

### Skill
One skill that fired during a session.

```
Skill {
  name:           string
  fired_at:       timestamp
  matched_by:     string  (why it was triggered)
}
```

### Comparison
A before/after pair for proving improvement.

```
Comparison {
  id:             string
  label:          string  (e.g. "knowledge tree refactor — March 2026")
  baseline:       Session[]
  optimized:      Session[]
  notes:          string
}
```

---

## Interfaces (Draft)

### CLI (first target)
```bash
agentrace log [session-json]    # log a session from JSON
agentrace sessions              # list recent sessions
agentrace show [session-id]     # detail view of one session
agentrace compare [before] [after]  # diff two sessions or groups
agentrace stats                 # aggregate: avg tokens, top skills, etc.
```

### Ingest — Claude Code session files (no hook needed)

Claude Code stores full NDJSON session logs at:
```
~/.claude/projects/{escaped-cwd}/{session-id}.jsonl
```

Each line is a session event. Key fields:

```json
{
  "sessionId": "e927ea8e-...",
  "timestamp": "2026-03-09T03:18:19.307Z",
  "type": "assistant",
  "cwd": "/Users/ryan/workspace/capacity",
  "gitBranch": "main",
  "slug": "mighty-munching-goose",
  "message": {
    "model": "claude-opus-4-6",
    "usage": {
      "input_tokens": 1,
      "cache_creation_input_tokens": 28774,
      "cache_read_input_tokens": 20411,
      "output_tokens": 2240
    },
    "content": [{ "type": "tool_use", "name": "Read", "input": { "file_path": "..." } }]
  },
  "toolUseResult": {
    "file": { "filePath": "/Users/ryan/workspace/capacity/AGENTS.md" }
  }
}
```

**What we can extract automatically:**
- All files read (`Read` tool calls → `toolUseResult.file.filePath`)
- Token counts per message (sum across session for totals)
- Cache hit vs. miss breakdown (`cache_read_input_tokens` vs `cache_creation_input_tokens`)
- Session duration (first timestamp → last timestamp)
- Working directory + git branch
- Model used
- Session slug (human-readable name)

**No self-reporting. No hooks. Just parse the files.**

### Storage (options)
- **SQLite** — simplest, local, no infra. Good for personal use.
- **Postgres** — if it becomes a team tool with a web UI.
- **JSON files** — ultra-portable, git-trackable, no DB required.

Start with SQLite + flat JSON export. Upgrade if needed.

---

## Roadmap

### Phase 1 — Local CLI
- Data schema finalized
- `agentrace log` ingests a session (JSON or structured args)
- `agentrace sessions` lists recent sessions with token counts
- `agentrace compare` shows before/after diff
- SQLite storage, no server required

### Phase 2 — OpenClaw Integration
- OpenClaw emits session events at end of each Hexed session
- Agentrace auto-ingests: context files, token counts, skills fired
- Zero manual logging for OpenClaw users

### Phase 3 — Team Dashboard
- Web UI: session feed, skill usage heatmap, comparison view
- Multi-user: each team member's sessions aggregated
- Export: shareable reports for stakeholders

### Phase 4 — Benchmarking
- Define "task templates" — same prompt run before and after an optimization
- Automated comparison pipeline
- Statistical significance on improvements

---

## Open Questions

1. **How do we get token counts?** Claude Code / OpenClaw may expose these;
   otherwise we estimate from file sizes. Exact numbers are ideal but estimates
   are still useful for comparisons.

2. **What's the right storage format for v1?** Leaning toward SQLite + JSON export.
   Simple, portable, no server needed for a team of 5.

3. **Should Agentrace be a library (imported) or a service (runs separately)?**
   Starting as a standalone CLI is lower friction. Library bindings come later.

4. **How do you define "outcome quality"?** Quantitative proxies (files changed,
   tests passing) are tractable. Human ratings are useful but add friction.
   Start with quantitative; add rating later.
