"""
cli.py — Command-line interface for agentrace

Usage:
    agentrace sessions [--project PATH]
    agentrace show SESSION_ID
    agentrace stats [--project PATH]
"""

import sys
from pathlib import Path
from .parser import find_sessions, parse_session_file


def cmd_sessions(project_path: str | None = None):
    """List recent Claude Code sessions with token counts."""
    files = find_sessions(project_path)
    if not files:
        print("No sessions found.")
        return

    # Parse and sort by start time
    sessions = []
    for f in files:
        try:
            s = parse_session_file(f)
            sessions.append(s)
        except Exception as e:
            print(f"  [skip] {f.name}: {e}", file=sys.stderr)

    sessions.sort(key=lambda s: s.started_at or "", reverse=True)

    print(f"\n{'SESSION':<38} {'SLUG':<28} {'MODEL':<20} {'FILES':>5} {'TOKENS':>8} {'MIN':>5}")
    print("-" * 110)
    for s in sessions[:20]:
        duration = f"{s.duration_seconds / 60:.0f}" if s.duration_seconds else "?"
        model_short = (s.model or "?").replace("claude-", "").replace("anthropic/", "")
        print(
            f"{s.session_id[:36]:<38} "
            f"{s.slug[:26]:<28} "
            f"{model_short[:18]:<20} "
            f"{len(s.unique_files):>5} "
            f"{s.usage.total:>8,} "
            f"{duration:>5}"
        )
    print()


def cmd_show(session_id: str, project_path: str | None = None):
    """Show detail for a single session."""
    files = find_sessions(project_path)
    match = None
    for f in files:
        if session_id in f.name:
            match = f
            break

    if not match:
        print(f"Session '{session_id}' not found.")
        return

    s = parse_session_file(match)
    print(f"\n── Session: {s.session_id}")
    print(f"   Slug:    {s.slug}")
    print(f"   Project: {s.cwd}")
    print(f"   Branch:  {s.git_branch or '—'}")
    print(f"   Model:   {s.model or '—'}")
    print(f"   Started: {s.started_at}")
    print(f"   Ended:   {s.ended_at}")
    if s.duration_seconds:
        print(f"   Duration: {s.duration_seconds / 60:.1f} min")

    print(f"\n── Tokens")
    print(f"   Input (fresh):   {s.usage.input_tokens:>8,}")
    print(f"   Cache created:   {s.usage.cache_creation_tokens:>8,}")
    print(f"   Cache hits:      {s.usage.cache_read_tokens:>8,}")
    print(f"   Output:          {s.usage.output_tokens:>8,}")
    print(f"   Total:           {s.usage.total:>8,}")

    print(f"\n── Context files ({len(s.unique_files)} unique)")
    for fp in s.unique_files:
        print(f"   {fp}")
    print()


def cmd_stats(project_path: str | None = None):
    """Aggregate stats across sessions."""
    files = find_sessions(project_path)
    if not files:
        print("No sessions found.")
        return

    sessions = []
    for f in files:
        try:
            sessions.append(parse_session_file(f))
        except Exception:
            pass

    if not sessions:
        print("No sessions parsed successfully.")
        return

    total_tokens = sum(s.usage.total for s in sessions)
    total_files = sum(len(s.unique_files) for s in sessions)
    avg_tokens = total_tokens // len(sessions)
    avg_files = total_files // len(sessions)

    # File frequency
    file_counts: dict[str, int] = {}
    for s in sessions:
        for fp in s.unique_files:
            file_counts[fp] = file_counts.get(fp, 0) + 1

    top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    print(f"\n── Stats across {len(sessions)} sessions")
    print(f"   Total tokens:    {total_tokens:>10,}")
    print(f"   Avg per session: {avg_tokens:>10,}")
    print(f"   Avg files read:  {avg_files:>10}")

    print(f"\n── Most-loaded context files")
    for fp, count in top_files:
        bar = "█" * min(count, 40)
        print(f"   {count:>4}x  {bar}  {fp}")
    print()


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: agentrace <sessions|show|stats> [options]")
        return

    cmd = args[0]
    rest = args[1:]

    if cmd == "sessions":
        project = rest[0] if rest else None
        cmd_sessions(project)
    elif cmd == "show":
        if not rest:
            print("Usage: agentrace show <session-id>")
            return
        cmd_show(rest[0])
    elif cmd == "stats":
        project = rest[0] if rest else None
        cmd_stats(project)
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: sessions, show, stats")


if __name__ == "__main__":
    main()
