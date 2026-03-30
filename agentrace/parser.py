"""
parser.py — Read Claude Code session NDJSON files from ~/.claude/projects/

Claude Code stores sessions at:
    ~/.claude/projects/{url-escaped-cwd}/{session-id}.jsonl

Each line is a JSON object representing one event in the session.
"""

import json
import re
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
    name: Optional[str] = None
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

    @property
    def project_name(self) -> str:
        """Human-readable project name from cwd."""
        return Path(self.cwd).name if self.cwd else "unknown"

    @property
    def date(self) -> str:
        if not self.started_at:
            return "?"
        return self.started_at[:10]


# ── Projects directory ────────────────────────────────────────────────────────

def get_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _real_cwd_from_dir(project_dir: Path) -> Optional[str]:
    """Read the actual cwd from any event in any session file in this dir."""
    for f in project_dir.glob("*.jsonl"):
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    cwd = event.get("cwd")
                    if cwd:
                        return cwd
        except Exception:
            continue
    return None


@dataclass
class ProjectSummary:
    escaped_name: str
    real_path: str
    session_count: int
    total_tokens: int
    last_active: Optional[str]


def list_projects() -> list[ProjectSummary]:
    """List all Claude Code projects with aggregate stats."""
    d = get_projects_dir()
    if not d.exists():
        return []

    results = []
    for project_dir in sorted(d.iterdir()):
        if not project_dir.is_dir():
            continue
        files = list(project_dir.glob("*.jsonl"))
        if not files:
            continue

        real_path = _real_cwd_from_dir(project_dir) or project_dir.name
        total_tokens = 0
        last_active = None

        for f in files:
            try:
                s = parse_session_file(f)
                total_tokens += s.usage.total
                if s.ended_at:
                    if last_active is None or s.ended_at > last_active:
                        last_active = s.ended_at
            except Exception:
                continue

        results.append(ProjectSummary(
            escaped_name=project_dir.name,
            real_path=real_path,
            session_count=len(files),
            total_tokens=total_tokens,
            last_active=last_active[:10] if last_active else None,
        ))

    results.sort(key=lambda p: p.last_active or "", reverse=True)
    return results


# ── Session finder ────────────────────────────────────────────────────────────

def find_sessions(project_path: Optional[str] = None,
                  claude_dir: Optional[Path] = None) -> list[Path]:
    """
    Find Claude Code session files.

    project_path: real filesystem path (e.g. /Users/ryan/workspace/capacity)
                  If None, returns sessions for ALL projects.
    claude_dir:   override for ~/.claude/projects/
    """
    if claude_dir is None:
        claude_dir = get_projects_dir()

    if not claude_dir.exists():
        return []

    if project_path:
        escaped = project_path.replace("/", "-").lstrip("-")
        project_dir = claude_dir / escaped
        if not project_dir.exists():
            return []
        dirs = [project_dir]
    else:
        dirs = [d for d in claude_dir.iterdir() if d.is_dir()]

    files = []
    for d in dirs:
        files.extend(d.glob("*.jsonl"))

    return files


def detect_project() -> Optional[str]:
    """
    Auto-detect the current project from cwd.
    Returns the real path if a matching Claude Code project directory exists.
    """
    import os
    cwd = os.getcwd()
    escaped = cwd.replace("/", "-").lstrip("-")
    project_dir = get_projects_dir() / escaped
    if project_dir.exists() and any(project_dir.glob("*.jsonl")):
        return cwd
    return None


# ── Session loader with numbering ─────────────────────────────────────────────

def load_sessions_sorted(project_path: Optional[str] = None) -> list[Session]:
    """Load all sessions sorted by date descending (index 0 = most recent = #1)."""
    files = find_sessions(project_path)
    sessions = []
    for f in files:
        try:
            sessions.append(parse_session_file(f))
        except Exception:
            continue
    sessions.sort(key=lambda s: s.started_at or "", reverse=True)
    return sessions


def resolve_session_ref(ref: str, sessions: list[Session]) -> Optional[Session]:
    """
    Resolve a session reference to a Session.

    Accepts:
      - A 1-based integer index: "1" = most recent, "2" = second most recent, …
      - A UUID prefix: "e927ea8e" matches session starting with that string
      - A slug prefix: "mighty" matches slug starting with that string
    """
    # Try numeric index
    if ref.isdigit():
        idx = int(ref) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
        return None

    # Try UUID or slug prefix
    for s in sessions:
        if s.session_id.startswith(ref) or (s.slug and s.slug.startswith(ref)):
            return s

    return None


# ── Name inference ────────────────────────────────────────────────────────────

_BOILERPLATE_RE = re.compile(
    r"^Read\s+(AGENTS|CLAUDE)\.md\b", re.IGNORECASE
)


def _first_meaningful_line(text: str) -> Optional[str]:
    """Return the first non-empty, non-boilerplate line from text."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading markdown header markers
        line = re.sub(r"^#+\s*", "", line).strip()
        if not line:
            continue
        if _BOILERPLATE_RE.match(line):
            continue
        return line[:60].rstrip()
    return None


def _infer_session_name(events: list[dict]) -> Optional[str]:
    """
    Resolve a human-readable session name.

    Strategy (in priority order):
      1. Explicit /rename via agent-name event  ← authoritative, user-defined
      2. queue-operation / enqueue content      ← programmatic task prompt
      3. First user message text block          ← interactive session fallback
    """
    # Strategy 1: explicit /rename — type="agent-name", field="agentName"
    # Use the LAST one if the user renamed multiple times
    renamed = None
    for e in events:
        if e.get("type") == "agent-name" and e.get("agentName"):
            renamed = e["agentName"]
    if renamed:
        return renamed[:60].rstrip()

    # Strategy 2: queue-operation enqueue
    for e in events:
        if e.get("type") == "queue-operation" and e.get("operation") == "enqueue":
            content = e.get("content", "")
            if content:
                name = _first_meaningful_line(content)
                if name:
                    return name

    # Strategy 2: first user message
    for e in events:
        msg = e.get("message", {})
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    name = _first_meaningful_line(block.get("text", ""))
                    if name:
                        return name
        elif isinstance(content, str) and content:
            name = _first_meaningful_line(content)
            if name:
                return name

    return None


# ── File parser ───────────────────────────────────────────────────────────────

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

    first = events[0]
    session_id = first.get("sessionId", path.stem)
    slug = first.get("slug", "")
    cwd = first.get("cwd", "")
    git_branch = first.get("gitBranch")

    timestamps = [e["timestamp"] for e in events if "timestamp" in e]
    started_at = min(timestamps) if timestamps else None
    ended_at = max(timestamps) if timestamps else None

    model = None
    for e in events:
        msg = e.get("message", {})
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            model = msg.get("model")
            if model:
                break

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
        name=_infer_session_name(events),
        context_files=context_files,
        usage=usage,
    )
