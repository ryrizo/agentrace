#!/usr/bin/env python3
"""
agentrace — iTerm2 Status Bar via session variable

Sets user.agentrace_status on all sessions every 30s.
Use in status bar: Interpolated String → \(user.agentrace_status)
  (no parentheses — it's a variable, not a function call)
"""

import asyncio
import json
import time
from pathlib import Path
import iterm2

PROJECTS_DIR = Path.home() / ".claude" / "projects"

_PRICING = {
    "opus":   (15.00, 1.50, 3.75, 75.00),
    "sonnet": ( 3.00, 0.30, 0.375, 15.00),
    "haiku":  ( 0.80, 0.08, 0.20,   4.00),
}

def _model_key(model):
    m = (model or "").lower()
    if "opus" in m: return "opus"
    if "haiku" in m: return "haiku"
    return "sonnet"

def _fmt_tokens(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}k"
    return str(n)

def _fmt_cost(d):
    return f"${d:.2f}" if d >= 0.01 else f"{d*100:.1f}c"

def _parse_latest():
    if not PROJECTS_DIR.exists():
        return None
    candidates = []
    for pd in PROJECTS_DIR.iterdir():
        if not pd.is_dir(): continue
        for f in pd.glob("*.jsonl"):
            try: candidates.append((f.stat().st_mtime, f))
            except OSError: pass
    if not candidates:
        return None
    candidates.sort(reverse=True)
    mtime, path = candidates[0]
    events = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try: events.append(json.loads(line))
                    except: pass
    except: return None
    if not events: return None
    model = None
    ti = to = cc = cr = 0
    for e in events:
        msg = e.get("message", {})
        if isinstance(msg, dict):
            if not model and msg.get("role") == "assistant":
                model = msg.get("model")
            u = msg.get("usage", {})
            if u:
                ti += u.get("input_tokens", 0)
                to += u.get("output_tokens", 0)
                cc += u.get("cache_creation_input_tokens", 0)
                cr += u.get("cache_read_input_tokens", 0)
    total = ti + to + cc + cr
    key = _model_key(model)
    p_in, p_cr, p_cw, p_out = _PRICING[key]
    cost = ti/1e6*p_in + cr/1e6*p_cr + cc/1e6*p_cw + to/1e6*p_out
    return {"tokens": total, "cost": cost, "mtime": mtime}

def _status(data):
    if not data: return "◌ agentrace"
    age = time.time() - data["mtime"]
    tok = _fmt_tokens(data["tokens"])
    cost = _fmt_cost(data["cost"])
    if age < 300:   return f"⚡ {tok}  {cost}  ●"
    if age < 7200:  return f"✓ {tok}  {cost}  {int(age/60)}m"
    return f"◌ {tok}  {cost}"

async def main(connection):
    app = await iterm2.async_get_app(connection)
    print("agentrace: connected, starting update loop")

    while True:
        data = _parse_latest()
        text = _status(data)
        print(f"agentrace: setting user.agentrace_status = {text!r}")

        for window in app.windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    try:
                        await session.async_set_variable("user.agentrace_status", text)
                    except Exception as e:
                        print(f"agentrace: error setting variable: {e}")

        await asyncio.sleep(30)

iterm2.run_forever(main)
