"""
cli.py — Command-line interface for agentrace

Usage:
    agentrace projects                    List all Claude Code projects
    agentrace sessions [PROJECT]          List sessions (#1 = most recent)
    agentrace show SESSION                Full detail (number, UUID prefix, or slug)
    agentrace stats [PROJECT]             Aggregate stats + most-loaded files
    agentrace compare SESSION_A SESSION_B Diff two sessions
    agentrace files [PROJECT]             Context file cost analysis
    agentrace watch [PROJECT]             Live session monitor

PROJECT can be a path (/Users/ryan/workspace/foo) or omitted to auto-detect from cwd.
SESSION can be a number (#1), UUID prefix (e927), or slug prefix (mighty).
"""

import sys
from pathlib import Path
from .parser import (
    find_sessions, load_sessions_sorted, parse_session_file,
    resolve_session_ref, list_projects, detect_project, Session
)
from .cost import session_cost, fmt_cost
from .display import (
    Spinner, box, section, rule, color_bar, mini_bar, fmt_tokens, short,
    RESET, BOLD, DIM, GREEN, YELLOW, RED, CYAN, GOLD, MUTED,
)
from .watcher import watch as _watch
from . import cmd_files as _cmd_files
from . import cmd_tree as _cmd_tree
from . import cmd_recommend as _cmd_recommend
from . import cmd_diff as _cmd_diff
from . import cmd_water as _cmd_water


# ── Helpers ───────────────────────────────────────────────────────────────────

def _short(path: str) -> str:
    home = str(Path.home())
    return ("~" + path[len(home):]) if path.startswith(home) else path


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


def _token_delta(a: int, b: int) -> str:
    diff = b - a
    if diff == 0:
        return "—"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:,}"


def _resolve_project(args: list[str]) -> tuple[str | None, list[str]]:
    """
    Extract optional project arg from args list.
    If no arg given, try to auto-detect from cwd.
    Returns (project_path_or_None, remaining_args).
    """
    # If first arg looks like a path, use it
    if args and (args[0].startswith("/") or args[0].startswith("~")):
        return args[0], args[1:]
    # Auto-detect from cwd
    detected = detect_project()
    return detected, args


def _get_sessions(project: str | None) -> list[Session]:
    sessions = load_sessions_sorted(project)
    if not sessions and project:
        # Try without scoping — maybe detection was wrong
        sessions = load_sessions_sorted(None)
    return sessions


def _resolve(ref: str, sessions: list[Session]) -> Session | None:
    s = resolve_session_ref(ref, sessions)
    if not s:
        print(f"Session '{ref}' not found. Use 'agentrace sessions' to list available sessions.")
    return s


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_projects():
    """List all Claude Code projects with session counts and token totals."""
    projects = list_projects()
    if not projects:
        print("No Claude Code projects found in ~/.claude/projects/")
        return

    print(f"\n{'#':<4} {'PROJECT':<45} {'SESSIONS':>8} {'TOKENS':>12} {'LAST ACTIVE':>12}")
    print("-" * 86)
    for i, p in enumerate(projects, 1):
        short = _short(p.real_path)
        last = p.last_active or "?"
        print(
            f"{i:<4} {short:<45} {p.session_count:>8} "
            f"{_fmt_tokens(p.total_tokens):>12} {last:>12}"
        )
    print()


def cmd_sessions(project: str | None = None):
    """List sessions with numbers, slugs, tokens, and duration."""
    sessions = _get_sessions(project)
    if not sessions:
        print("No sessions found.")
        if not project:
            print("Tip: run from inside a project directory, or pass a project path.")
        return

    scope = _short(project) if project else "all projects"
    print(f"\nSessions — {scope}\n")
    print(f"{'#':<5} {'DATE':<12} {'SLUG':<30} {'MODEL':<18} {'FILES':>5} {'TOKENS':>10} {'COST':>8} {'MIN':>5}")
    print("-" * 100)

    for i, s in enumerate(sessions, 1):
        duration = f"{s.duration_seconds / 60:.0f}" if s.duration_seconds else "?"
        model_short = (s.model or "?").replace("claude-", "").replace("anthropic/", "")
        slug = s.slug[:28] if s.slug else f"({s.session_id[:8]})"
        cost = fmt_cost(session_cost(s))
        print(
            f"#{i:<4} {s.date:<12} {slug:<30} {model_short[:16]:<18} "
            f"{len(s.unique_files):>5} {_fmt_tokens(s.usage.total):>10} {cost:>8} {duration:>5}"
        )
    print(f"\nTip: use the # to reference a session  →  agentrace show 1  |  agentrace compare 1 3\n")


def cmd_show(ref: str, project: str | None = None):
    """Show full detail for a session."""
    sessions = _get_sessions(project)
    s = _resolve(ref, sessions)
    if not s:
        return

    idx = sessions.index(s) + 1
    cache_pct = 0
    if s.usage.total_input > 0:
        cache_pct = s.usage.cache_read_tokens / s.usage.total_input * 100

    print(f"\n── Session #{idx}  {s.slug or ''}")
    print(f"   ID:       {s.session_id}")
    print(f"   Project:  {_short(s.cwd)}")
    print(f"   Branch:   {s.git_branch or '—'}")
    print(f"   Model:    {s.model or '—'}")
    print(f"   Date:     {s.date}")
    if s.duration_seconds:
        print(f"   Duration: {s.duration_seconds / 60:.1f} min")

    print(f"\n── Tokens")
    print(f"   Input (fresh):   {s.usage.input_tokens:>10,}")
    print(f"   Cache created:   {s.usage.cache_creation_tokens:>10,}")
    print(f"   Cache hits:      {s.usage.cache_read_tokens:>10,}  ({cache_pct:.0f}% of input)")
    print(f"   Output:          {s.usage.output_tokens:>10,}")
    print(f"   Total:           {s.usage.total:>10,}")

    cost = session_cost(s)
    model_short = (s.model or "?").replace("claude-", "").replace("anthropic/", "")
    print(f"\n── Cost")
    print(f"   Estimated:    {fmt_cost(cost)}")
    print(f"   ({model_short} pricing)")

    print(f"\n── Context files ({len(s.unique_files)} unique)")
    for fp in s.unique_files:
        print(f"   {_short(fp)}")
    print()


def cmd_stats(project: str | None = None):
    """Aggregate stats across sessions with rich visual display."""

    with Spinner("Crunching session data"):
        sessions = _get_sessions(project)

    if not sessions:
        print("\n  No sessions found.\n")
        return

    # ── Compute aggregates ──────────────────────────────────────────────────
    total_tokens = sum(s.usage.total for s in sessions)
    avg_tokens   = total_tokens // len(sessions)
    avg_files    = sum(len(s.unique_files) for s in sessions) // len(sessions)
    total_input  = sum(s.usage.total_input for s in sessions)
    total_cache  = sum(s.usage.cache_read_tokens for s in sessions)
    cache_pct    = (total_cache / total_input * 100) if total_input > 0 else 0
    total_cost   = sum(session_cost(s) for s in sessions)
    avg_cost     = total_cost / len(sessions) if sessions else 0.0

    file_counts: dict[str, int] = {}
    for s in sessions:
        for fp in s.unique_files:
            file_counts[fp] = file_counts.get(fp, 0) + 1
    top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Date range
    dated = [s for s in sessions if s.started_at]
    if dated:
        dates = sorted(s.started_at[:10] for s in dated)
        date_range = f"{dates[0]} → {dates[-1]}" if dates[0] != dates[-1] else dates[0]
    else:
        date_range = "—"

    scope = _short(project) if project else "all projects"

    # ── Header ──────────────────────────────────────────────────────────────
    print()
    print(box(
        f"📈  Stats  {scope}",
        f"{len(sessions)} sessions  ·  {date_range}",
    ))

    # ── Key numbers ─────────────────────────────────────────────────────────
    print(section("Key numbers"))

    if cache_pct >= 80:
        cache_color = GREEN
    elif cache_pct >= 50:
        cache_color = YELLOW
    else:
        cache_color = RED

    col_w = 14  # right-align numbers in this width

    def num(val: str) -> str:
        return f"{BOLD}{val}{RESET}"

    def lbl(val: str) -> str:
        return f"{DIM}{val}{RESET}"

    def cost_num(val: str) -> str:
        return f"{GOLD}{BOLD}{val}{RESET}"

    rows = [
        (num(fmt_tokens(total_tokens)), lbl("total tokens"),
         cost_num(fmt_cost(total_cost)),  lbl("total cost")),
        (num(fmt_tokens(avg_tokens)),   lbl("avg / session"),
         cost_num(fmt_cost(avg_cost)),   lbl("avg / session")),
        (num(str(avg_files)),           lbl("avg files"),
         f"{cache_color}{BOLD}{cache_pct:.0f}%{RESET}", lbl("cache hit rate")),
    ]
    for (n1, l1, n2, l2) in rows:
        print(f"    {n1:>30}  {l1:<28}  {n2:>30}  {l2}")

    # ── Most-loaded files ────────────────────────────────────────────────────
    if top_files:
        print()
        print(rule())
        print(section("Most-loaded context files"))

        max_count = top_files[0][1] if top_files else 1
        for fp, count in top_files:
            bar = color_bar(count / max_count, width=24)
            short_path = short(fp)
            parts = short_path.rsplit("/", 1)
            if len(parts) == 2:
                path_display = f"{DIM}{parts[0]}/{RESET}{BOLD}{parts[1]}{RESET}"
            else:
                path_display = f"{BOLD}{short_path}{RESET}"
            print(f"  {BOLD}{count}×{RESET}  {bar}  {path_display}")

    # ── Sessions over time ───────────────────────────────────────────────────
    chronological = sorted(dated, key=lambda s: s.started_at or "")
    if chronological:
        print()
        print(rule())
        print(section("Sessions over time"))

        max_tok = max(s.usage.total for s in chronological) or 1

        for s in chronological:
            idx = sessions.index(s) + 1
            bar = mini_bar(s.usage.total / max_tok, width=24)
            cache_p = 0.0
            if s.usage.total_input > 0:
                cache_p = s.usage.cache_read_tokens / s.usage.total_input * 100
            dur = f"{s.duration_seconds/60:.0f}m" if s.duration_seconds else "?"
            cost_s = session_cost(s)
            print(
                f"  {DIM}#{idx:<3}{RESET}  {DIM}{s.date}{RESET}  {bar}  "
                f"{BOLD}{fmt_tokens(s.usage.total):>6}{RESET}  "
                f"{GOLD}{fmt_cost(cost_s):>7}{RESET}  "
                f"{DIM}cache{RESET} {cache_p:>2.0f}%  "
                f"{DIM}{dur}{RESET}"
            )

        # Trend
        print()
        print(rule())
        if len(chronological) >= 4:
            mid = len(chronological) // 2
            first_avg  = sum(s.usage.total for s in chronological[:mid]) / mid
            second_avg = sum(s.usage.total for s in chronological[mid:]) / (len(chronological) - mid)
            delta_pct  = (second_avg - first_avg) / first_avg * 100
            if abs(delta_pct) >= 5:
                arrow     = "↑" if delta_pct > 0 else "↓"
                direction = "increasing" if delta_pct > 0 else "decreasing"
                verdict   = "context growing" if delta_pct > 0 else "context shrinking ✓"
                trend_color = YELLOW if delta_pct > 0 else GREEN
                print(
                    f"\n  {trend_color}{BOLD}{arrow} Tokens {direction} {abs(delta_pct):.0f}%"
                    f"{RESET}  {DIM}·  {verdict}{RESET}"
                )
            else:
                print(f"\n  {DIM}→ Token usage is stable across sessions{RESET}")
        else:
            print(f"\n  {DIM}Not enough sessions to calculate trend{RESET}")

    # ── Insights ─────────────────────────────────────────────────────────────
    insights = []
    if cache_pct < 50:
        insights.append(
            f"💡 {DIM}Low cache rate — consider pinning frequently-loaded files to CLAUDE.md{RESET}"
        )
    if top_files:
        top_fp, top_count = top_files[0]
        total_file_loads = sum(c for _, c in file_counts.items())
        if total_file_loads > 0 and top_count / total_file_loads > 0.20:
            fname = short(top_fp).rsplit("/", 1)[-1]
            insights.append(
                f"💡 {BOLD}{fname}{RESET}{DIM} dominates context — prime candidate for splitting{RESET}"
            )
    if insights:
        print()
        for tip in insights:
            print(f"  {tip}")

    print()


def cmd_compare(ref_a: str, ref_b: str, project: str | None = None):
    """Diff two sessions side by side."""
    sessions = _get_sessions(project)
    a = _resolve(ref_a, sessions)
    b = _resolve(ref_b, sessions)
    if not a or not b:
        return

    idx_a = sessions.index(a) + 1
    idx_b = sessions.index(b) + 1
    label_a = f"#{idx_a} {a.slug or a.session_id[:8]}"
    label_b = f"#{idx_b} {b.slug or b.session_id[:8]}"

    print(f"\n── Compare")
    print(f"   A: {label_a}  ({a.date})")
    print(f"   B: {label_b}  ({b.date})")

    print(f"\n── Tokens              {'A':>12}  {'B':>12}  {'DELTA':>12}")
    print(f"   {'─' * 52}")

    def row(label: str, va: int, vb: int, lower_is_better: bool = True):
        delta = _token_delta(va, vb)
        if va == vb:
            flag = ""
        elif (vb < va) == lower_is_better:
            flag = " ✓"
        else:
            flag = " ✗"
        print(f"   {label:<18}  {va:>12,}  {vb:>12,}  {delta:>12}{flag}")

    row("Total", a.usage.total, b.usage.total)
    row("Input (fresh)", a.usage.input_tokens, b.usage.input_tokens)
    row("Cache created", a.usage.cache_creation_tokens, b.usage.cache_creation_tokens)
    row("Cache hits", a.usage.cache_read_tokens, b.usage.cache_read_tokens, lower_is_better=False)
    row("Output", a.usage.output_tokens, b.usage.output_tokens)

    cost_a = session_cost(a)
    cost_b = session_cost(b)
    cost_delta = cost_b - cost_a
    if cost_delta < 0:
        cost_delta_str = f"-{fmt_cost(abs(cost_delta))}"
        cost_flag = " ✓"
    elif cost_delta > 0:
        cost_delta_str = f"+{fmt_cost(cost_delta)}"
        cost_flag = " ✗"
    else:
        cost_delta_str = "—"
        cost_flag = ""
    print(f"   {'Est. cost':<18}  {fmt_cost(cost_a):>12}  {fmt_cost(cost_b):>12}  {cost_delta_str:>12}{cost_flag}")

    a_cache = (a.usage.cache_read_tokens / a.usage.total_input * 100) if a.usage.total_input else 0
    b_cache = (b.usage.cache_read_tokens / b.usage.total_input * 100) if b.usage.total_input else 0
    flag = " ✓" if b_cache > a_cache else (" ✗" if b_cache < a_cache else "")
    print(f"   {'Cache hit rate':<18}  {a_cache:>11.0f}%  {b_cache:>11.0f}%{flag}")

    if a.duration_seconds and b.duration_seconds:
        row("Duration (sec)", int(a.duration_seconds), int(b.duration_seconds))

    set_a, set_b = set(a.unique_files), set(b.unique_files)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    both = sorted(set_a & set_b)

    print(f"\n── Context files  (A: {len(set_a)}  B: {len(set_b)})")
    if both:
        print(f"\n   In both ({len(both)})")
        for fp in both:
            print(f"     {_short(fp)}")
    if only_a:
        print(f"\n   Only in A — not in B ({len(only_a)})")
        for fp in only_a:
            print(f"     − {_short(fp)}")
    if only_b:
        print(f"\n   Only in B — not in A ({len(only_b)})")
        for fp in only_b:
            print(f"     + {_short(fp)}")

    delta_t = b.usage.total - a.usage.total
    delta_f = len(set_b) - len(set_a)
    print(f"\n── Summary")
    if delta_t < 0:
        print(f"   B used {abs(delta_t):,} fewer tokens ({abs(delta_t)/a.usage.total*100:.0f}% reduction) ✓")
    elif delta_t > 0:
        print(f"   B used {delta_t:,} more tokens ({delta_t/a.usage.total*100:.0f}% increase)")
    else:
        print(f"   Token usage identical")
    if delta_f < 0:
        print(f"   B loaded {abs(delta_f)} fewer context file(s) ✓")
    elif delta_f > 0:
        print(f"   B loaded {delta_f} more context file(s)")
    else:
        print(f"   Same number of context files")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def cmd_help():
    """Print detailed help for all commands."""
    print("""
agentrace — observability for Claude Code sessions
Reads ~/.claude/projects/ directly. No config needed.

COMMANDS

  projects
      List all Claude Code projects with session counts,
      total tokens, and last active date.

  sessions [PROJECT]
      List sessions numbered most-recent-first.
      Omit PROJECT to auto-detect from current directory.

  show SESSION [PROJECT]
      Full detail for one session: token breakdown (fresh vs cached),
      cache hit rate, duration, and every context file loaded.

  stats [PROJECT]
      Aggregate stats across all sessions: total tokens, averages,
      cache hit rate, and a bar chart of most-loaded context files.

  compare SESSION_A SESSION_B [PROJECT]
      Diff two sessions side by side. Shows token delta per category,
      cache efficiency change, and which context files were added or
      removed. The core command for proving context optimization worked.

  files [PROJECT]
      Context file cost analysis — ranked by total token spend.
      Shows which files are most expensive, how often they're loaded,
      estimated tokens per load, and files no longer on disk.

  watch [PROJECT]
      Live session monitor. Waits for a new Claude Code session to
      start, then tails it in real-time — file loads, edits, execs,
      and running token count. Run in a split terminal alongside Claude.

  tree [PROJECT]
      Detect co-load clusters across sessions and visualize your context
      tree. Shows which files are loaded together, estimates token savings,
      and optionally writes a CLAUDE.md skeleton to encode the tree.

  recommend [PROJECT]
      Analyze context file usage and produce actionable recommendations:
      what to pin in CLAUDE.md, what to load on-demand, what to split,
      and what dead references to clean up.

  diff [PROJECT]
      Correlate git commits to AGENTS.md/CLAUDE.md with session token
      trends. Shows whether each context change actually helped reduce
      token usage.

  water [PROJECT]
      Estimate water consumption equivalent for your token usage.
      Based on data center cooling research (~22,500 gal / 1B tokens).

  help
      Show this message.

REFERENCING SESSIONS
  #number     most recent = #1  (agentrace show 1)
  UUID prefix  first 4+ chars   (agentrace show e927)
  slug prefix  first word       (agentrace compare mighty brave)

REFERENCING PROJECTS
  Pass a path:  agentrace sessions ~/workspace/myproject
  Auto-detect:  run agentrace from inside the project directory

EXAMPLES
  agentrace projects
  agentrace sessions
  agentrace show 1
  agentrace compare 1 3
  agentrace stats ~/workspace/capacity
  agentrace files
  agentrace watch
  agentrace tree
  agentrace recommend
  agentrace diff
  agentrace water
""")


def main():
    args = sys.argv[1:]
    if not args:
        cmd_help()
        return

    cmd = args[0]
    rest = args[1:]

    if cmd in ("help", "--help", "-h"):
        cmd_help()

    elif cmd == "projects":
        cmd_projects()

    elif cmd == "sessions":
        project, _ = _resolve_project(rest)
        cmd_sessions(project)

    elif cmd == "show":
        if not rest:
            print("Usage: agentrace show SESSION [PROJECT]")
            return
        project, remaining = _resolve_project(rest[1:])
        cmd_show(rest[0], project)

    elif cmd == "stats":
        project, _ = _resolve_project(rest)
        cmd_stats(project)

    elif cmd == "compare":
        if len(rest) < 2:
            print("Usage: agentrace compare SESSION_A SESSION_B [PROJECT]")
            return
        project, _ = _resolve_project(rest[2:])
        cmd_compare(rest[0], rest[1], project)

    elif cmd == "files":
        project, _ = _resolve_project(rest)
        _cmd_files.run(project)

    elif cmd == "tree":
        project, _ = _resolve_project(rest)
        _cmd_tree.run(project)

    elif cmd == "watch":
        project, _ = _resolve_project(rest)
        _watch(project)

    elif cmd == "recommend":
        project, _ = _resolve_project(rest)
        _cmd_recommend.run(project)

    elif cmd == "diff":
        project, _ = _resolve_project(rest)
        _cmd_diff.run(project)

    elif cmd == "water":
        project, _ = _resolve_project(rest)
        _cmd_water.run(project)

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: projects, sessions, show, stats, compare, files, watch, recommend, diff, water")


if __name__ == "__main__":
    main()
