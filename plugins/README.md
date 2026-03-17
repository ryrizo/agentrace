# Agentrace Plugins

Optional integrations that extend agentrace beyond the core CLI.

---

## iTerm2 Status Bar Component

Shows live Claude Code session stats directly in your iTerm2 status bar.

```
⚡ 1.2M  $1.84  ●          ← active session (modified < 5 min ago)
✓ 847k   $0.63  14m ago    ← recent session
◌ agentrace                ← nothing recent
```

Hover shows a tooltip with session slug, model, cache hit rate, and file count.
Updates every 30 seconds. Optionally filters to a specific project.

### Install

**Step 1 — Enable iTerm2 Python API**

```
iTerm2 → Settings → General → Magic → ✅ Enable Python API
```

**Step 2 — Copy the script**

```bash
mkdir -p ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch
cp plugins/iterm2_statusbar.py \
   ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch/agentrace_statusbar.py
```

**Step 3 — Restart iTerm2**

iTerm2 will auto-launch the script on startup. You should see it listed under:
```
iTerm2 → Scripts → agentrace_statusbar (running)
```

**Step 4 — Add to your status bar**

```
iTerm2 → Settings → Profiles → [your profile] → Session → Status Bar Enabled ✅
→ Configure Status Bar
→ Drag "Agentrace" from Available Components into the bar
→ OK
```

**Optional: Filter to a project**

Click the Agentrace component in the Configure Status Bar dialog to set a
project path filter (e.g. `/Users/you/workspace/myproject`). When set, only
sessions from that project are shown.

### How it works

The script runs in iTerm2's own Python environment and reads
`~/.claude/projects/` directly — the same NDJSON files the CLI parses.
It's fully self-contained: no `agentrace` import needed, no network calls.

### Uninstall

```bash
rm ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch/agentrace_statusbar.py
```

Then remove the component from your status bar in iTerm2 settings.

---

## Planned plugins

- **Shell completion** — tab-complete commands and session IDs in zsh/bash
- **Inline charts** — render token trend charts as images using iTerm2's
  inline image protocol (`imgcat`-style)
