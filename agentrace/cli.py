"""
cli.py — Command-line interface for agentrace

Usage:
    agentrace sessions [PROJECT_PATH]   List recent sessions with token counts
    agentrace show SESSION_ID           Full detail for one session
    agentrace stats [PROJECT_PATH]      Aggregate stats + most-loaded files
    agentrace compare ID_A ID_B         Diff two sessions side by side
"""

import sys
from pathlib import Path
from .parser import find_sessions, parse_session_file, Session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_session(session_id: str) -> Session | None:
    for f in find_sessions():
        if session_id in f.name:
            try:
                return parse_session_file(f)
            except Exception:
                return None
    return None


def _short_path(full_path: str) -> str:
    """Shorten a path for display — strip common home prefix."""
    home = str(Path.home())
    if full_path.startswith(home):
        return "~" + full_path[len(home):]
    return full_path


def _token_delta(a: int, b: int) -> str:
    diff = b - a
    if diff == 0:
        return "  —"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:,}"


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_sessions(project_path: str | None = None):
    """List recent Claude Code sessions with token counts."""
    files = find_sessions(project_path)
    if not files:
        print("No sessions found.")
        return

    sessions = []
    for f in files:
        try:
            sessions.append(parse_session_file(f))
        except Exception as e:
            print(f"  [skip] {f.name}: {e}", file=sys.stderr)

    sessions.sort(key=lambda s: s.started_at or "", reverse=True)

    print(f"\n{'SESSION':<38} {'SLUG':<28} {'MODEL':<22} {'FILES':>5} {'TOKENS':>10} {'MIN':>5}")
    print("-" * 115)
    for s in sessions[:20]:
        duration = f"{s.duration_seconds / 60:.0f}" if s.duration_seconds else "?"
        model_short = (s.model or "?").replace("claude-", "").replace("anthropic/", "")
        slug = s.slug[:26] if s.slug else "(no slug)"
        print(
            f"{s.session_id[:36]:<38} "
            f"{slug:<28} "
            f"{model_short[:20]:<22} "
            f"{len(s.unique_files):>5} "
            f"{s.usage.total:>10,} "
            f"{duration:>5}"
        )
    print()


def cmd_show(session_id: str):
    """Show full detail for a single session."""
    s = _find_session(session_id)
    if not s:
        print(f"Session '{session_id}' not found.")
        return

    print(f"\n── Session: {s.session_id}")
    print(f"   Slug:     {s.slug or '(none)'}")
    print(f"   Project:  {_short_path(s.cwd)}")
    print(f"   Branch:   {s.git_branch or '—'}")
    print(f"   Model:    {s.model or '—'}")
    print(f"   Started:  {s.started_at}")
    print(f"   Ended:    {s.ended_at}")
    if s.duration_seconds:
        print(f"   Duration: {s.duration_seconds / 60:.1f} min")

    print(f"\n── Tokens")
    cache_pct = 0
    if s.usage.total_input > 0:
        cache_pct = (s.usage.cache_read_tokens / s.usage.total_input) * 100
    print(f"   Input (fresh):   {s.usage.input_tokens:>10,}")
    print(f"   Cache created:   {s.usage.cache_creation_tokens:>10,}")
    print(f"   Cache hits:      {s.usage.cache_read_tokens:>10,}  ({cache_pct:.0f}% of input)")
    print(f"   Output:          {s.usage.output_tokens:>10,}")
    print(f"   Total:           {s.usage.total:>10,}")

    print(f"\n── Context files ({len(s.unique_files)} unique)")
    for fp in s.unique_files:
        print(f"   {_short_path(fp)}")
    print()


def cmd_stats(project_path: str | None = None):
    """Aggregate stats across all sessions."""
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

    total_cache_hits = sum(s.usage.cache_read_tokens for s in sessions)
    total_input = sum(s.usage.total_input for s in sessions)
    cache_pct = (total_cache_hits / total_input * 100) if total_input > 0 else 0

    file_counts: dict[str, int] = {}
    for s in sessions:
        for fp in s.unique_files:
            file_counts[fp] = file_counts.get(fp, 0) + 1

    top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    print(f"\n── Stats across {len(sessions)} sessions")
    print(f"   Total tokens:      {total_tokens:>10,}")
    print(f"   Avg per session:   {avg_tokens:>10,}")
    print(f"   Avg files read:    {avg_files:>10}")
    print(f"   Cache hit rate:    {cache_pct:>9.0f}%")

    print(f"\n── Most-loaded context files")
    for fp, count in top_files:
        bar = "█" * min(count, 40)
        print(f"   {count:>4}x  {bar}  {_short_path(fp)}")
    print()


def cmd_compare(id_a: str, id_b: str):
    """Diff two sessions — tokens, cache efficiency, context files."""
    a = _find_session(id_a)
    b = _find_session(id_b)

    if not a:
        print(f"Session '{id_a}' not found.")
        return
    if not b:
        print(f"Session '{id_b}' not found.")
        return

    slug_a = a.slug or a.session_id[:8]
    slug_b = b.slug or b.session_id[:8]

    print(f"\n── Compare")
    print(f"   A: {a.session_id[:8]}  {slug_a}  ({a.started_at[:10] if a.started_at else '?'})")
    print(f"   B: {b.session_id[:8]}  {slug_b}  ({b.started_at[:10] if b.started_at else '?'})")

    # Token comparison
    print(f"\n── Tokens              {'A':>12}  {'B':>12}  {'DELTA':>10}")
    print(f"   {'─' * 50}")

    def row(label: str, va: int, vb: int):
        delta = _token_delta(va, vb)
        better = " ✓" if vb < va else (" ✗" if vb > va else "")
        print(f"   {label:<18}  {va:>12,}  {vb:>12,}  {delta:>10}{better}")

    row("Total", a.usage.total, b.usage.total)
    row("Input (fresh)", a.usage.input_tokens, b.usage.input_tokens)
    row("Cache created", a.usage.cache_creation_tokens, b.usage.cache_creation_tokens)
    row("Cache hits", a.usage.cache_read_tokens, b.usage.cache_read_tokens)
    row("Output", a.usage.output_tokens, b.usage.output_tokens)

    a_cache_pct = (a.usage.cache_read_tokens / a.usage.total_input * 100) if a.usage.total_input > 0 else 0
    b_cache_pct = (b.usage.cache_read_tokens / b.usage.total_input * 100) if b.usage.total_input > 0 else 0
    better = " ✓" if b_cache_pct > a_cache_pct else ""
    print(f"   {'Cache hit rate':<18}  {a_cache_pct:>11.0f}%  {b_cache_pct:>11.0f}%  {better}")

    # Duration
    if a.duration_seconds and b.duration_seconds:
        row("Duration (sec)", int(a.duration_seconds), int(b.duration_seconds))

    # Context file diff
    set_a = set(a.unique_files)
    set_b = set(b.unique_files)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    both = sorted(set_a & set_b)

    print(f"\n── Context files  (A: {len(set_a)}  B: {len(set_b)})")

    if both:
        print(f"\n   In both ({len(both)})")
        for fp in both:
            print(f"     {_short_path(fp)}")

    if only_a:
        print(f"\n   Only in A — removed in B ({len(only_a)})")
        for fp in only_a:
            print(f"     − {_short_path(fp)}")

    if only_b:
        print(f"\n   Only in B — added vs A ({len(only_b)})")
        for fp in only_b:
            print(f"     + {_short_path(fp)}")

    # Summary verdict
    delta_tokens = b.usage.total - a.usage.total
    delta_files = len(set_b) - len(set_a)
    print(f"\n── Summary")
    if delta_tokens < 0:
        print(f"   B used {abs(delta_tokens):,} fewer tokens ({abs(delta_tokens)/a.usage.total*100:.0f}% reduction) ✓")
    elif delta_tokens > 0:
        print(f"   B used {delta_tokens:,} more tokens ({delta_tokens/a.usage.total*100:.0f}% increase)")
    else:
        print(f"   Token usage identical")

    if delta_files < 0:
        print(f"   B loaded {abs(delta_files)} fewer context file(s) ✓")
    elif delta_files > 0:
        print(f"   B loaded {delta_files} more context file(s)")
    else:
        print(f"   Same number of context files")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: agentrace <sessions|show|stats|compare> [args]")
        print("       agentrace sessions [PROJECT_PATH]")
        print("       agentrace show SESSION_ID")
        print("       agentrace stats [PROJECT_PATH]")
        print("       agentrace compare SESSION_A SESSION_B")
        return

    cmd = args[0]
    rest = args[1:]

    if cmd == "sessions":
        cmd_sessions(rest[0] if rest else None)
    elif cmd == "show":
        if not rest:
            print("Usage: agentrace show <session-id>")
            return
        cmd_show(rest[0])
    elif cmd == "stats":
        cmd_stats(rest[0] if rest else None)
    elif cmd == "compare":
        if len(rest) < 2:
            print("Usage: agentrace compare <session-a> <session-b>")
            return
        cmd_compare(rest[0], rest[1])
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: sessions, show, stats, compare")


if __name__ == "__main__":
    main()
