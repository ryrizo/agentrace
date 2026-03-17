#!/usr/bin/env python3
"""
agentrace — iTerm2 Status Bar Component

Shows live Claude Code session stats in your iTerm2 status bar:
  ⚡ 1.2M  $1.84  ● active
  ✓ 847k   $0.63  ○ 14m ago
  ◌ no recent session

INSTALL
-------
1. Enable iTerm2 Python API:
   iTerm2 → Settings → General → Magic → Enable Python API ✓

2. Install this script:
   cp plugins/iterm2_statusbar.py \
      ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch/agentrace_statusbar.py

3. Restart iTerm2, or run manually:
   iTerm2 → Scripts → agentrace_statusbar

4. Add to status bar:
   iTerm2 → Settings → Profiles → [your profile] → Session → Status Bar
   → Configure Status Bar → drag "Agentrace" component into the bar

OPTIONAL: Filter to a specific project path via the component knob.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import iterm2


# ── Inline token parser (no agentrace import needed) ─────────────────────────

PROJECTS_DIR = Path.home() / ".claude" / "projects"

_PRICING = {
    "opus":   (15.00, 1.50, 3.75, 75.00),
    "sonnet": ( 3.00, 0.30, 0.375, 15.00),
    "haiku":  ( 0.80, 0.08, 0.20,   4.00),
}

def _model_key(model: str | None) -> str:
    if not model:
        return "sonnet"
    m = (model or "").lower()
    if "opus" in m:
        return "opus"
    if "haiku" in m:
        return "haiku"
    return "sonnet"

def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)

def _fmt_cost(dollars: float) -> str:
    if dollars < 0.01:
        return f"{dollars*100:.1f}¢"
    return f"${dollars:.2f}"


def _parse_latest_session(project_filter: str | None = None) -> dict | None:
    """
    Find the most recently modified session file and parse its stats.
    Returns a dict with: tokens, cost, model, slug, modified_at, files_loaded
    """
    if not PROJECTS_DIR.exists():
        return None

    # Find all session files, optionally filtered by project
    candidates = []
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        if project_filter:
            escaped = project_filter.replace("/", "-").lstrip("-")
            if escaped not in project_dir.name:
                continue
        for f in project_dir.glob("*.jsonl"):
            try:
                candidates.append((f.stat().st_mtime, f))
            except OSError:
                pass

    if not candidates:
        return None

    candidates.sort(reverse=True)
    latest_path = candidates[0][1]
    modified_at = candidates[0][0]

    # Parse the session file
    events = []
    try:
        with open(latest_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        return None

    if not events:
        return None

    first = events[0]
    slug = first.get("slug", "")
    model = None
    tokens_in = 0
    tokens_out = 0
    cache_create = 0
    cache_read = 0
    files: set[str] = set()

    for e in events:
        msg = e.get("message", {})
        if isinstance(msg, dict):
            if not model and msg.get("role") == "assistant":
                model = msg.get("model")
            u = msg.get("usage", {})
            if u:
                tokens_in    += u.get("input_tokens", 0)
                tokens_out   += u.get("output_tokens", 0)
                cache_create += u.get("cache_creation_input_tokens", 0)
                cache_read   += u.get("cache_read_input_tokens", 0)

        result = e.get("toolUseResult", {})
        if isinstance(result, dict):
            fp = result.get("file", {}).get("filePath")
            if fp:
                files.add(fp)

    total = tokens_in + tokens_out + cache_create + cache_read
    key = _model_key(model)
    p_in, p_cr, p_cw, p_out = _PRICING[key]
    cost = (
        tokens_in    / 1_000_000 * p_in  +
        cache_read   / 1_000_000 * p_cr  +
        cache_create / 1_000_000 * p_cw  +
        tokens_out   / 1_000_000 * p_out
    )

    return {
        "tokens": total,
        "cost": cost,
        "model": model,
        "slug": slug,
        "modified_at": modified_at,
        "files_loaded": len(files),
        "cache_pct": int(cache_read / (tokens_in + cache_create + cache_read) * 100)
                     if (tokens_in + cache_create + cache_read) > 0 else 0,
    }


def _status_text(data: dict | None) -> str:
    """Format the compact status bar string."""
    if data is None:
        return "◌ agentrace"

    age_seconds = time.time() - data["modified_at"]

    tok = _fmt_tokens(data["tokens"])
    cost = _fmt_cost(data["cost"])

    if age_seconds < 300:  # < 5 min → active
        return f"⚡ {tok}  {cost}  ●"
    elif age_seconds < 7200:  # < 2hr → recent
        mins = int(age_seconds / 60)
        return f"✓ {tok}  {cost}  {mins}m ago"
    else:
        return f"◌ {tok}  {cost}  idle"


def _tooltip_text(data: dict | None) -> str:
    """Format the detailed hover/tooltip string."""
    if data is None:
        return "No recent Claude Code sessions found."

    age_seconds = time.time() - data["modified_at"]
    slug = data["slug"] or "unnamed session"
    model_short = (data["model"] or "unknown").replace("claude-", "").replace("anthropic/", "")

    lines = [
        f"agentrace",
        f"",
        f"Session: {slug}",
        f"Model:   {model_short}",
        f"Tokens:  {_fmt_tokens(data['tokens'])}",
        f"Cost:    {_fmt_cost(data['cost'])}",
        f"Cache:   {data['cache_pct']}% hit rate",
        f"Files:   {data['files_loaded']} loaded",
    ]

    if age_seconds < 60:
        lines.append("Status:  ● active now")
    elif age_seconds < 3600:
        lines.append(f"Status:  {int(age_seconds/60)}m ago")
    else:
        lines.append(f"Status:  {int(age_seconds/3600)}h ago")

    return "\n".join(lines)


# ── iTerm2 registration ───────────────────────────────────────────────────────

async def main(connection):
    component = iterm2.StatusBarComponent(
        short_description="Agentrace",
        detailed_description="Claude Code token & cost tracker",
        knobs=[
            iterm2.StringKnob(
                "Project filter (optional path)",
                placeholder="e.g. /Users/you/workspace/myproject",
                default_value="",
                key="project_filter",
            )
        ],
        exemplar="⚡ 1.2M  $1.84  ●",
        update_cadence=30,
        identifier="com.agentrace.statusbar",
    )

    @iterm2.RPC
    async def coro(knobs):
        project_filter = knobs.get("project_filter", "").strip() or None
        data = _parse_latest_session(project_filter)
        return _status_text(data)

    await component.async_register(connection, coro)


iterm2.run_forever(main)
