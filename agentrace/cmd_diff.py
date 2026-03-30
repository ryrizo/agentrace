"""
cmd_diff.py — Git correlation for context changes.

Correlates commits to AGENTS.md/CLAUDE.md with session cost trends.
For each commit that touched context docs, compares avg token usage
before vs after to show whether the change helped.
"""

import json
import subprocess
from datetime import datetime
from .parser import load_sessions_sorted, find_sessions, Session
from .cost import session_cost, fmt_cost
from .display import (
    short, fmt_tokens, color_bar, rule, section, box,
    RESET, BOLD, DIM, GREEN, YELLOW, RED, CYAN, ORANGE, GOLD, MUTED
)


def _find_project_cwd(project: str | None, sessions: list[Session]) -> str | None:
    """
    Find the real project cwd.

    Strategy (in order):
    1. Use explicit project arg if given
    2. Scan Session.cwd fields (usually empty — parser reads first event only)
    3. Scan context file paths to find common prefix (most reliable fallback)
    4. Scan NDJSON events directly for a cwd field
    """
    if project:
        return project

    # Try any non-empty cwd in loaded sessions
    for s in sessions:
        if s.cwd:
            return s.cwd

    # Derive from context file paths — find most common leading path component
    all_files: list[str] = []
    for s in sessions:
        all_files.extend(s.unique_files)

    if all_files:
        from pathlib import Path as _Path
        # Count frequency of each directory ancestor
        ancestor_counts: dict[str, int] = {}
        for fp in all_files:
            p = _Path(fp)
            for parent in p.parents:
                ps = str(parent)
                if ps not in ("/", ""):
                    ancestor_counts[ps] = ancestor_counts.get(ps, 0) + 1
        if ancestor_counts:
            # The most common deep ancestor is likely the project root
            candidates = sorted(ancestor_counts.items(), key=lambda x: (-x[1], -len(x[0])))
            return candidates[0][0]

    # Last resort: scan NDJSON files for a cwd field (may find wrong project if multi-project)
    session_files = find_sessions(project)
    for f in session_files:
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


def _run_git(cwd: str, *args: str) -> str | None:
    """Run a git command in cwd. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _parse_iso(ts: str) -> datetime | None:
    """Parse ISO-8601 timestamp (from git or session)."""
    # Handle git format: 2026-03-17 14:30:00 +0000
    # Handle session format: 2026-03-17T14:30:00.000Z
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _session_dt(s: Session) -> datetime | None:
    if not s.started_at:
        return None
    return _parse_iso(s.started_at)


def _avg_tokens(sessions: list[Session]) -> float:
    if not sessions:
        return 0.0
    return sum(s.total_usage.total for s in sessions) / len(sessions)


def _avg_cost(sessions: list[Session]) -> float:
    if not sessions:
        return 0.0
    return sum(session_cost(s) for s in sessions) / len(sessions)


def run(project: str | None = None):
    from .display import Spinner

    with Spinner("Loading sessions"):
        sessions = load_sessions_sorted(project)

    if not sessions:
        print("\n  No sessions found.\n")
        return

    # Find the project cwd — scan NDJSON events since parser only reads first event
    cwd = _find_project_cwd(project, sessions)
    if not cwd:
        print("\n  Could not determine project path — pass a project path explicitly.\n")
        print("  Example: agentrace diff ~/workspace/myproject\n")
        return

    scope = short(project) if project else short(cwd)

    print()
    print(box(
        "🔀  Git Correlation",
        f"AGENTS.md / CLAUDE.md  ·  {scope}"
    ))

    # Run git log
    git_out = _run_git(cwd, "log", "--format=%H|%ai|%s", "--", "AGENTS.md", "CLAUDE.md")

    if not git_out:
        print(f"\n  {YELLOW}No commits found for AGENTS.md or CLAUDE.md.{RESET}")
        print(f"\n  {DIM}Tip: versioning your context docs lets agentrace measure{RESET}")
        print(f"  {DIM}whether each change actually reduced token usage.{RESET}")
        print(f"\n  {DIM}Try:{RESET}  git add AGENTS.md CLAUDE.md && git commit -m 'docs: context setup'")
        print()
        return

    # Parse commits
    commits = []
    for line in git_out.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, ts, subject = parts
        dt = _parse_iso(ts.strip())
        if dt:
            commits.append((sha.strip(), dt, subject.strip()))

    if not commits:
        print(f"\n  {YELLOW}Could not parse commit history.{RESET}\n")
        return

    # Sort sessions chronologically
    dated_sessions = [(s, _session_dt(s)) for s in sessions if _session_dt(s)]
    if not dated_sessions:
        print(f"\n  {YELLOW}Sessions have no timestamps — cannot correlate.{RESET}\n")
        return

    print(section("  Commits to context docs  →  token impact"))

    # For each commit, split sessions into before/after
    for sha, commit_dt, subject in commits:
        # Normalize commit_dt for comparison (make it offset-naive if needed)
        if commit_dt.tzinfo is not None:
            # Convert to naive UTC for comparison
            import datetime as _dt
            commit_naive = commit_dt.replace(tzinfo=None) - _dt.timedelta(
                seconds=commit_dt.utcoffset().total_seconds() if commit_dt.utcoffset() else 0
            )
        else:
            commit_naive = commit_dt

        before = []
        after  = []
        for s, sdt in dated_sessions:
            if sdt is None:
                continue
            # Normalize session dt
            if sdt.tzinfo is not None:
                import datetime as _dt2
                sdt_naive = sdt.replace(tzinfo=None) - _dt2.timedelta(
                    seconds=sdt.utcoffset().total_seconds() if sdt.utcoffset() else 0
                )
            else:
                sdt_naive = sdt

            if sdt_naive < commit_naive:
                before.append(s)
            else:
                after.append(s)

        avg_before = _avg_tokens(before)
        avg_after  = _avg_tokens(after)

        # Subject truncated
        subj = subject[:52] + "…" if len(subject) > 52 else subject
        date_str = commit_dt.strftime("%Y-%m-%d")
        sha_short = sha[:8]

        print(f"  {BOLD}{sha_short}{RESET}  {DIM}{date_str}{RESET}  {subj}")

        if not before and not after:
            print(f"  {DIM}  (no sessions to compare){RESET}\n")
            continue

        if not before:
            print(f"  {DIM}  {len(after)} sessions after  ·  no sessions before to compare{RESET}")
            if after:
                print(f"  {DIM}  avg tokens after:  {fmt_tokens(int(avg_after))}{RESET}")
            print()
            continue

        if not after:
            print(f"  {DIM}  {len(before)} sessions before  ·  no sessions after to compare{RESET}")
            if before:
                print(f"  {DIM}  avg tokens before: {fmt_tokens(int(avg_before))}{RESET}")
            print()
            continue

        # Both before and after exist
        delta_pct = ((avg_after - avg_before) / avg_before * 100) if avg_before > 0 else 0.0
        direction = "↓" if delta_pct < 0 else "↑"
        color = GREEN if delta_pct < 0 else RED
        verdict = f"{color}{BOLD}{abs(delta_pct):.0f}% {direction}{RESET}"
        flag = f"  {GREEN}✓ helped{RESET}" if delta_pct < -5 else (
               f"  {RED}✗ got worse{RESET}" if delta_pct > 5 else
               f"  {DIM}~ no significant change{RESET}")

        # Mini bar showing before/after ratio
        max_avg = max(avg_before, avg_after) or 1
        bar_before = color_bar(avg_before / max_avg, width=16)
        bar_after  = color_bar(avg_after  / max_avg, width=16)

        print(f"  {DIM}  before ({len(before)} sessions):{RESET}  {bar_before}  {fmt_tokens(int(avg_before))} avg")
        print(f"  {DIM}  after  ({len(after)} sessions):{RESET}  {bar_after}  {fmt_tokens(int(avg_after))} avg  {verdict}{flag}")

        # Cost comparison
        cost_before = _avg_cost(before)
        cost_after  = _avg_cost(after)
        cost_delta  = cost_after - cost_before
        if abs(cost_delta) > 0.001:
            cost_sign = "-" if cost_delta < 0 else "+"
            print(f"  {DIM}  cost change:  {cost_sign}{fmt_cost(abs(cost_delta))}/session avg{RESET}")
        print()

    # ── Overall trend ─────────────────────────────────────────────────────────
    print(rule())
    total = len(dated_sessions)
    if total >= 4:
        mid = total // 2
        # dated_sessions is ordered most-recent first (from load_sessions_sorted)
        # Reverse to get chronological order
        chron = list(reversed(dated_sessions))
        first_half  = [s for s, _ in chron[:mid]]
        second_half = [s for s, _ in chron[mid:]]
        avg_first  = _avg_tokens(first_half)
        avg_second = _avg_tokens(second_half)
        if avg_first > 0:
            overall_delta = (avg_second - avg_first) / avg_first * 100
            direction = "↓" if overall_delta < 0 else "↑"
            color = GREEN if overall_delta < 0 else RED
            print(f"\n  {DIM}Overall trend across {total} sessions:{RESET}  "
                  f"{color}{BOLD}{abs(overall_delta):.0f}% {direction}{RESET}  "
                  f"{DIM}(first half avg {fmt_tokens(int(avg_first))}  →  second half avg {fmt_tokens(int(avg_second))}){RESET}")

    print()
