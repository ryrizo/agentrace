"""
watcher.py — Live session monitor for Claude Code

Watches ~/.claude/projects/ for a new session to start, then tails it
line-by-line and prints events as they arrive.

Usage:
    agentrace watch                       # watch for any new session
    agentrace watch PROJECT_PATH          # watch for a session in a specific project
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from .parser import find_sessions, parse_session_file, ContextFile, TokenUsage


# ── ANSI colors (graceful fallback if terminal doesn't support them) ──────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
BLUE   = "\033[34m"
PURPLE = "\033[35m"


def _short(path: str) -> str:
    home = str(Path.home())
    return ("~" + path[len(home):]) if path.startswith(home) else path


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


# ── Event renderer ────────────────────────────────────────────────────────────

class LiveSession:
    """Accumulates state from a streaming session and renders events."""

    def __init__(self, session_id: str, slug: str, cwd: str):
        self.session_id = session_id
        self.slug = slug
        self.cwd = cwd
        self.usage = TokenUsage()
        self.files_seen: list[str] = []
        self.files_set: set[str] = set()
        self.message_count = 0
        self.started_at = datetime.now()

    def handle_event(self, event: dict):
        etype = event.get("type", "")
        msg = event.get("message", {})
        timestamp = event.get("timestamp", "")

        # File read
        result = event.get("toolUseResult", {})
        if isinstance(result, dict):
            file_info = result.get("file", {})
            if isinstance(file_info, dict):
                fp = file_info.get("filePath")
                if fp and fp not in self.files_set:
                    self.files_set.add(fp)
                    self.files_seen.append(fp)
                    short = _short(fp)
                    print(f"  {DIM}{_now()}{RESET}  {CYAN}📄 loaded{RESET}  {short}")

        # Tool call (exec, write, edit)
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    tool = block.get("name", "")
                    inp = block.get("input", {})

                    if tool == "exec" and "command" in inp:
                        cmd = inp["command"][:60]
                        print(f"  {DIM}{_now()}{RESET}  {YELLOW}⚡ exec{RESET}     {cmd}")
                    elif tool in ("Write", "Edit") and "file_path" in inp:
                        print(f"  {DIM}{_now()}{RESET}  {GREEN}✏  {tool.lower()}{RESET}    {_short(inp['file_path'])}")
                    elif tool == "Read":
                        pass  # Covered by toolUseResult above

            # Token usage
            usage = msg.get("usage", {})
            if usage:
                prev_total = self.usage.total
                self.usage.input_tokens += usage.get("input_tokens", 0)
                self.usage.output_tokens += usage.get("output_tokens", 0)
                self.usage.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
                self.usage.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
                self.message_count += 1

                # Print token update every message
                cache_pct = 0
                if self.usage.total_input > 0:
                    cache_pct = self.usage.cache_read_tokens / self.usage.total_input * 100
                print(
                    f"  {DIM}{_now()}{RESET}  {PURPLE}◈ tokens{RESET}   "
                    f"total {BOLD}{_fmt_tokens(self.usage.total)}{RESET}  "
                    f"cache {cache_pct:.0f}%  "
                    f"out {_fmt_tokens(self.usage.output_tokens)}"
                )

    def print_header(self):
        slug_display = f"  {BOLD}{self.slug}{RESET}" if self.slug else ""
        print(f"\n{BOLD}{GREEN}● Session started{RESET}{slug_display}")
        print(f"  {DIM}id:   {self.session_id[:8]}{RESET}")
        print(f"  {DIM}cwd:  {_short(self.cwd)}{RESET}")
        print()

    def print_summary(self):
        elapsed = (datetime.now() - self.started_at).total_seconds()
        cache_pct = 0
        if self.usage.total_input > 0:
            cache_pct = self.usage.cache_read_tokens / self.usage.total_input * 100
        print(f"\n{BOLD}── Session ended{RESET}  {DIM}({elapsed/60:.1f} min){RESET}")
        print(f"   Tokens:     {BOLD}{_fmt_tokens(self.usage.total)}{RESET}  "
              f"(cache {cache_pct:.0f}%)")
        print(f"   Files read: {len(self.files_seen)}")
        print()


# ── File tailer ───────────────────────────────────────────────────────────────

def _tail_session(path: Path, live: LiveSession, from_start: bool = False):
    """
    Tail a growing JSONL file, calling live.handle_event() for each new line.

    from_start=True  → replay all existing lines first, then follow new ones
    from_start=False → seek to end, only show events from this point forward
    """
    with open(path) as f:
        if not from_start:
            f.seek(0, 2)  # jump to end for brand-new sessions
            print(f"  {DIM}Tailing {path.name}…{RESET}\n")
        else:
            print(f"  {DIM}Replaying session history…{RESET}\n")
        try:
            while True:
                line = f.readline()
                if not line:
                    if from_start:
                        # Switched to live-follow mode
                        from_start = False
                    time.sleep(0.2)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    live.handle_event(event)
                except json.JSONDecodeError:
                    pass
        except KeyboardInterrupt:
            pass


# ── Session detector ──────────────────────────────────────────────────────────

def _get_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _latest_session_file(project_path: str | None) -> Path | None:
    """Return the most recently modified .jsonl file."""
    if project_path:
        escaped = project_path.replace("/", "-").lstrip("-")
        dirs = [_get_projects_dir() / escaped]
    else:
        d = _get_projects_dir()
        dirs = [x for x in d.iterdir() if x.is_dir()] if d.exists() else []

    files = []
    for d in dirs:
        files.extend(d.glob("*.jsonl"))

    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def _find_active_session(project_path: str | None, max_age_seconds: int = 300) -> Path | None:
    """
    Return a session file that was modified within the last max_age_seconds.
    Used to auto-attach to an already-running session.
    """
    now = time.time()
    candidates = []

    if not _get_projects_dir().exists():
        return None

    for f in _get_projects_dir().rglob("*.jsonl"):
        if project_path:
            escaped = project_path.replace("/", "-").lstrip("-")
            if escaped not in str(f):
                continue
        try:
            age = now - f.stat().st_mtime
            if age <= max_age_seconds:
                candidates.append((age, f))
        except OSError:
            pass

    if not candidates:
        return None
    # Return the most recently modified
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def watch(project_path: str | None = None):
    """Watch for a new Claude Code session and tail it live."""
    print(f"\n{BOLD}agentrace watch{RESET}")
    if project_path:
        print(f"  {DIM}scope: {_short(project_path)}{RESET}")
    print(f"  {DIM}press Ctrl+C to stop{RESET}\n")

    known_files: set[str] = set()

    # Check for an already-active session before seeding known_files
    active = _find_active_session(project_path, max_age_seconds=300)
    if active:
        print(f"  {YELLOW}◈ Active session detected — attaching…{RESET}\n")
        try:
            with open(active) as fh:
                first_line = fh.readline().strip()
            first = json.loads(first_line) if first_line else {}
        except Exception:
            first = {}

        live = LiveSession(
            session_id=first.get("sessionId", active.stem),
            slug=first.get("slug", ""),
            cwd=first.get("cwd", ""),
        )
        live.print_header()
        _tail_session(active, live, from_start=True)
        live.print_summary()
        known_files.add(str(active))
        print(f"{DIM}Waiting for next session…{RESET}\n")
    else:
        print(f"  {DIM}waiting for a new Claude Code session…{RESET}\n")

    # Seed remaining known files so we don't replay old sessions
    for f in (_get_projects_dir().rglob("*.jsonl") if _get_projects_dir().exists() else []):
        known_files.add(str(f))

    try:
        while True:
            # Look for a new .jsonl file we haven't seen
            new_file = None
            if _get_projects_dir().exists():
                for f in _get_projects_dir().rglob("*.jsonl"):
                    if str(f) not in known_files:
                        # Check it matches the project scope
                        if project_path:
                            escaped = project_path.replace("/", "-").lstrip("-")
                            if escaped not in str(f):
                                continue
                        new_file = f
                        known_files.add(str(f))
                        break

            if new_file:
                # Read first line to get session metadata
                try:
                    with open(new_file) as fh:
                        first_line = fh.readline().strip()
                    first = json.loads(first_line) if first_line else {}
                except Exception:
                    first = {}

                live = LiveSession(
                    session_id=first.get("sessionId", new_file.stem),
                    slug=first.get("slug", ""),
                    cwd=first.get("cwd", ""),
                )
                live.print_header()
                _tail_session(new_file, live)
                live.print_summary()

                # After session ends, go back to waiting
                print(f"{DIM}Waiting for next session…{RESET}\n")
                known_files.add(str(new_file))

            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n{DIM}Stopped.{RESET}\n")
