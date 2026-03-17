"""
parser.py — Read Claude Code session NDJSON files from ~/.claude/projects/

Claude Code stores sessions at:
    ~/.claude/projects/{url-escaped-cwd}/{session-id}.jsonl

Each line is a JSON object representing one event in the session.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ContextFile:
    path: str
    timestamp: str


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def total(self) -> int:
        return self.total_input + self.output_tokens


@dataclass
class Session:
    session_id: str
    slug: str
    cwd: str
    git_branch: Optional[str]
    model: Optional[str]
    started_at: Optional[str]
    ended_at: Optional[str]
    context_files: list[ContextFile] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def duration_seconds(self) -> Optional[float]:
        if not self.started_at or not self.ended_at:
            return None
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        try:
            start = datetime.strptime(self.started_at, fmt)
            end = datetime.strptime(self.ended_at, fmt)
            return (end - start).total_seconds()
        except ValueError:
            return None

    @property
    def unique_files(self) -> list[str]:
        seen = set()
        out = []
        for f in self.context_files:
            if f.path not in seen:
                seen.add(f.path)
                out.append(f.path)
        return out


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_session_file(path: Path) -> Session:
    """Parse a single Claude Code NDJSON session file into a Session."""
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        raise ValueError(f"No events found in {path}")

    # Pull session metadata from first event
    first = events[0]
    session_id = first.get("sessionId", path.stem)
    slug = first.get("slug", "")
    cwd = first.get("cwd", "")
    git_branch = first.get("gitBranch")

    timestamps = [e["timestamp"] for e in events if "timestamp" in e]
    started_at = min(timestamps) if timestamps else None
    ended_at = max(timestamps) if timestamps else None

    # Extract model from first assistant message
    model = None
    for e in events:
        msg = e.get("message", {})
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            model = msg.get("model")
            if model:
                break

    # Accumulate token usage across all assistant messages
    usage = TokenUsage()
    for e in events:
        msg = e.get("message", {})
        if not isinstance(msg, dict):
            continue
        u = msg.get("usage", {})
        if not u:
            continue
        usage.input_tokens += u.get("input_tokens", 0)
        usage.output_tokens += u.get("output_tokens", 0)
        usage.cache_creation_tokens += u.get("cache_creation_input_tokens", 0)
        usage.cache_read_tokens += u.get("cache_read_input_tokens", 0)

    # Extract context files from Read tool calls
    context_files = []
    for e in events:
        timestamp = e.get("timestamp", "")
        result = e.get("toolUseResult", {})
        if isinstance(result, dict):
            file_info = result.get("file", {})
            if isinstance(file_info, dict):
                fp = file_info.get("filePath")
                if fp:
                    context_files.append(ContextFile(path=fp, timestamp=timestamp))

    return Session(
        session_id=session_id,
        slug=slug,
        cwd=cwd,
        git_branch=git_branch,
        model=model,
        started_at=started_at,
        ended_at=ended_at,
        context_files=context_files,
        usage=usage,
    )


def find_sessions(project_path: Optional[str] = None, claude_dir: Optional[Path] = None) -> list[Path]:
    """
    Find Claude Code session files for a given project path.

    If project_path is None, returns sessions for ALL projects.
    claude_dir defaults to ~/.claude/projects/
    """
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"

    if not claude_dir.exists():
        return []

    if project_path:
        # Escape the project path the same way Claude Code does
        escaped = project_path.replace("/", "-").lstrip("-")
        project_dir = claude_dir / escaped
        if not project_dir.exists():
            return []
        dirs = [project_dir]
    else:
        dirs = [d for d in claude_dir.iterdir() if d.is_dir()]

    files = []
    for d in dirs:
        files.extend(sorted(d.glob("*.jsonl")))

    return files
