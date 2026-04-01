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
from . import cmd_report as _cmd_report


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
    with Spinner("Loading sessions"):
        sessions = _get_sessions(project)

    if not sessions:
        print("No sessions found.")
        if not project:
            print("Tip: run from inside a project directory, or pass a project path.")
        return

    scope = _short(project) if project else "all projects"
    total_tokens = sum(s.total_usage.total for s in sessions)
    total_cost = sum(session_cost(s) for s in sessions)
    max_tok = max(s.total_usage.total for s in sessions) or 1

    print()
    print(box(
        f"📋  Sessions  {scope}",
        f"{len(sessions)} sessions  ·  {fmt_tokens(total_tokens)} tokens  ·  {fmt_cost(total_cost)} total",
    ))

    # Column header (widths: # 5, DATE 12, SLUG 32, FILES 5, bar+tok 16, COST 9, MIN 4)
    print(f"  {DIM}{'#':<5}  {'DATE':<12}  {'SLUG':<32}  {'FILES':>5}  {'':9}{'TOKENS':>7}  {'COST':>9}  {'MIN':>4}{RESET}")
    print(rule(78))

    for i, s in enumerate(sessions, 1):
        duration = f"{s.duration_seconds / 60:.0f}" if s.duration_seconds else "?"

        # # column — BOLD CYAN, padded to 5 visual chars
        num_str = f"#{i}"
        num_display = f"{BOLD}{CYAN}{num_str:<5}{RESET}"

        # DATE — DIM
        date_display = f"{DIM}{(s.date or '?'):<12}{RESET}"

        # SLUG — real slug normal; UUID-only DIM parens, padded to 32
        if s.slug:
            slug_str = s.slug[:30]
            slug_display = f"{slug_str:<32}"
        else:
            inner = f"({s.session_id[:8]})"
            slug_display = f"{DIM}{inner}{RESET}" + " " * (32 - len(inner))

        # FILES + optional agent count
        files_str = f"{len(s.unique_files)} files"
        if s.subagent_count > 0:
            files_str += f"  {DIM}+{s.subagent_count} agent{'s' if s.subagent_count != 1 else ''}{RESET}"
        files_display = files_str

        # TOKENS — mini_bar (width 8) + BOLD colored token count (right-aligned to 7)
        tok = s.total_usage.total
        tok_color = GREEN if tok < 500_000 else (YELLOW if tok < 2_000_000 else RED)
        tok_str = fmt_tokens(tok)
        bar = mini_bar(tok / max_tok, width=8)
        tok_display = f"{bar} {BOLD}{tok_color}{tok_str:>7}{RESET}"

        # COST — BOLD GOLD, right-aligned to 9
        cost_str = fmt_cost(session_cost(s))
        cost_display = f"{BOLD}{GOLD}{cost_str:>9}{RESET}"

        # MIN — DIM, right-aligned to 4
        dur_display = f"{DIM}{duration:>4}{RESET}"

        print(f"  {num_display}  {date_display}  {slug_display}  {files_display}  {tok_display}  {cost_display}  {dur_display}")

        # Session name subtitle
        if s.name:
            print(f"  {'':5}  {'':12}  {DIM}{s.name}{RESET}")

    print()
    print(f"  {DIM}agentrace show 1  ·  agentrace compare 2 5  ·  agentrace watch{RESET}")
    print()


def cmd_show(ref: str, project: str | None = None):
    """Show full detail for a session."""
    sessions = _get_sessions(project)
    s = _resolve(ref, sessions)
    if not s:
        return

    idx = sessions.index(s) + 1
    tu = s.total_usage
    cache_pct = 0
    if tu.total_input > 0:
        cache_pct = tu.cache_read_tokens / tu.total_input * 100

    print(f"\n── Session #{idx}  {s.slug or ''}")
    if s.name:
        print(f"   Name:     {s.name}")
    print(f"   ID:       {s.session_id}")
    print(f"   Project:  {_short(s.cwd)}")
    print(f"   Branch:   {s.git_branch or '—'}")
    print(f"   Model:    {s.model or '—'}")
    print(f"   Date:     {s.date}")
    if s.duration_seconds:
        print(f"   Duration: {s.duration_seconds / 60:.1f} min")

    print(f"\n── Tokens")
    if s.subagent_count > 0:
        print(f"   Orchestrator:")
        print(f"     Input (fresh):  {s.usage.input_tokens:>10,}")
        print(f"     Cache hits:     {s.usage.cache_read_tokens:>10,}")
        print(f"     Output:         {s.usage.output_tokens:>10,}")
        print(f"   Subagents ({s.subagent_count}):")
        print(f"     Input (fresh):  {s.subagent_usage.input_tokens:>10,}")
        print(f"     Cache hits:     {s.subagent_usage.cache_read_tokens:>10,}")
        print(f"     Output:         {s.subagent_usage.output_tokens:>10,}")
        print(f"   {'─' * 17}")
        print(f"   Total:            {tu.total:>10,}  ({cache_pct:.0f}% cache hits)")
    else:
        print(f"   Input (fresh):   {s.usage.input_tokens:>10,}")
        print(f"   Cache created:   {s.usage.cache_creation_tokens:>10,}")
        print(f"   Cache hits:      {s.usage.cache_read_tokens:>10,}  ({cache_pct:.0f}% of input)")
        print(f"   Output:          {s.usage.output_tokens:>10,}")
        print(f"   Total:           {tu.total:>10,}")

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
    total_tokens = sum(s.total_usage.total for s in sessions)
    avg_tokens   = total_tokens // len(sessions)
    avg_files    = sum(len(s.unique_files) for s in sessions) // len(sessions)
    total_input  = sum(s.total_usage.total_input for s in sessions)
    total_cache  = sum(s.total_usage.cache_read_tokens for s in sessions)
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

        max_tok = max(s.total_usage.total for s in chronological) or 1

        for s in chronological:
            idx = sessions.index(s) + 1
            bar = mini_bar(s.total_usage.total / max_tok, width=24)
            cache_p = 0.0
            if s.total_usage.total_input > 0:
                cache_p = s.total_usage.cache_read_tokens / s.total_usage.total_input * 100
            dur = f"{s.duration_seconds/60:.0f}m" if s.duration_seconds else "?"
            cost_s = session_cost(s)
            print(
                f"  {DIM}#{idx:<3}{RESET}  {DIM}{s.date}{RESET}  {bar}  "
                f"{BOLD}{fmt_tokens(s.total_usage.total):>6}{RESET}  "
                f"{GOLD}{fmt_cost(cost_s):>7}{RESET}  "
                f"{DIM}cache{RESET} {cache_p:>2.0f}%  "
                f"{DIM}{dur}{RESET}"
            )
            if s.name:
                name_trunc = s.name[:52] + "…" if len(s.name) > 52 else s.name
                print(f"  {DIM}      {' ' * 11}  {name_trunc}{RESET}")

        # Trend
        print()
        print(rule())
        if len(chronological) >= 4:
            mid = len(chronological) // 2
            first_avg  = sum(s.total_usage.total for s in chronological[:mid]) / mid
            second_avg = sum(s.total_usage.total for s in chronological[mid:]) / (len(chronological) - mid)
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
    with Spinner("Comparing sessions"):
        sessions = _get_sessions(project)

    a = _resolve(ref_a, sessions)
    b = _resolve(ref_b, sessions)
    if not a or not b:
        return

    idx_a = sessions.index(a) + 1
    idx_b = sessions.index(b) + 1

    def _slug_label(s, idx):
        label = s.name or s.slug or s.session_id[:8]
        if len(label) > 32:
            label = label[:29] + "..."
        return f"#{idx} {label} ({s.date})"

    label_a = _slug_label(a, idx_a)
    label_b = _slug_label(b, idx_b)

    print()
    print(box(
        "⚖️   Compare",
        f"A: {label_a}  ·  B: {label_b}",
    ))

    # ── Token table ──────────────────────────────────────────────────────────
    print(section("Tokens"))
    print(f"  {DIM}  {'':18}  {'A':>12}  {'B':>12}  {'':12}  {'DELTA':>12}{RESET}")
    print(rule(72))

    cost_a = session_cost(a)
    cost_b = session_cost(b)
    a_cache = (a.total_usage.cache_read_tokens / a.total_usage.total_input * 100) if a.total_usage.total_input else 0
    b_cache = (b.total_usage.cache_read_tokens / b.total_usage.total_input * 100) if b.total_usage.total_input else 0

    def _delta_bar(va: float, vb: float) -> str:
        max_val = max(abs(va), abs(vb)) if max(abs(va), abs(vb)) > 0 else 1
        fraction = min(1.0, abs(vb - va) / max_val)
        return mini_bar(fraction, width=10)

    def int_row(label: str, va: int, vb: int, lower_is_better: bool = True):
        delta = vb - va
        if va == vb:
            delta_str = "—"
            delta_color = DIM
            flag = ""
        else:
            favorable = (vb < va) == lower_is_better
            sign = "+" if delta > 0 else ""
            delta_str = f"{sign}{delta:,}"
            delta_color = GREEN if favorable else RED
            flag = f"  {delta_color}{'✓' if favorable else '✗'}{RESET}"
        bar = _delta_bar(va, vb)
        print(
            f"   {label:<18}  {BOLD}{va:>12,}{RESET}  {BOLD}{vb:>12,}{RESET}"
            f"  {bar}  {BOLD}{delta_color}{delta_str:>12}{RESET}{flag}"
        )

    int_row("Total", a.total_usage.total, b.total_usage.total)
    int_row("Input (fresh)", a.total_usage.input_tokens, b.total_usage.input_tokens)
    int_row("Cache created", a.total_usage.cache_creation_tokens, b.total_usage.cache_creation_tokens)
    int_row("Cache hits", a.total_usage.cache_read_tokens, b.total_usage.cache_read_tokens, lower_is_better=False)
    int_row("Output", a.total_usage.output_tokens, b.total_usage.output_tokens)

    # Est. cost row — A and B in GOLD
    cost_delta = cost_b - cost_a
    if cost_delta < 0:
        cost_delta_str = f"-{fmt_cost(abs(cost_delta))}"
        cost_delta_color = GREEN
        cost_flag = f"  {GREEN}✓{RESET}"
    elif cost_delta > 0:
        cost_delta_str = f"+{fmt_cost(cost_delta)}"
        cost_delta_color = RED
        cost_flag = f"  {RED}✗{RESET}"
    else:
        cost_delta_str = "—"
        cost_delta_color = DIM
        cost_flag = ""
    bar = _delta_bar(cost_a, cost_b)
    print(
        f"   {'Est. cost':<18}  {BOLD}{GOLD}{fmt_cost(cost_a):>12}{RESET}"
        f"  {BOLD}{GOLD}{fmt_cost(cost_b):>12}{RESET}"
        f"  {bar}  {BOLD}{cost_delta_color}{cost_delta_str:>12}{RESET}{cost_flag}"
    )

    # Cache hit rate row — colored by threshold
    def _cache_color(pct: float) -> str:
        return GREEN if pct >= 80 else (YELLOW if pct >= 50 else RED)

    a_cc = _cache_color(a_cache)
    b_cc = _cache_color(b_cache)
    cache_delta = b_cache - a_cache
    if cache_delta > 0:
        cache_delta_str = f"+{cache_delta:.0f}%"
        cache_delta_color = GREEN
        cache_flag = f"  {GREEN}✓{RESET}"
    elif cache_delta < 0:
        cache_delta_str = f"{cache_delta:.0f}%"
        cache_delta_color = RED
        cache_flag = f"  {RED}✗{RESET}"
    else:
        cache_delta_str = "—"
        cache_delta_color = DIM
        cache_flag = ""
    bar = _delta_bar(a_cache, b_cache)
    print(
        f"   {'Cache hit rate':<18}  {BOLD}{a_cc}{a_cache:>11.0f}%{RESET}"
        f"  {BOLD}{b_cc}{b_cache:>11.0f}%{RESET}"
        f"  {bar}  {BOLD}{cache_delta_color}{cache_delta_str:>12}{RESET}{cache_flag}"
    )

    if a.duration_seconds and b.duration_seconds:
        int_row("Duration (sec)", int(a.duration_seconds), int(b.duration_seconds))

    # ── Context files ─────────────────────────────────────────────────────────
    set_a, set_b = set(a.unique_files), set(b.unique_files)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    both = sorted(set_a & set_b)

    print(section(f"Context files  (A: {len(set_a)}  B: {len(set_b)})"))

    def _path_parts(fp: str):
        sp = _short(fp)
        parts = sp.rsplit("/", 1)
        return (parts[0] + "/", parts[1]) if len(parts) == 2 else ("", sp)

    if both:
        for fp in both:
            d, fn = _path_parts(fp)
            print(f"   {DIM}·  {d}{RESET}{_short(fp).rsplit('/', 1)[-1]}")
    if only_a:
        if both:
            print()
        for fp in only_a:
            d, fn = _path_parts(fp)
            print(f"   {RED}−{RESET}  {DIM}{d}{RESET}{BOLD}{fn}{RESET}")
    if only_b:
        if both or only_a:
            print()
        for fp in only_b:
            d, fn = _path_parts(fp)
            print(f"   {GREEN}+{RESET}  {DIM}{d}{RESET}{BOLD}{fn}{RESET}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(rule(60))
    print()

    delta_t = b.total_usage.total - a.total_usage.total
    delta_f = len(set_b) - len(set_a)

    if delta_t < 0:
        pct = abs(delta_t) / a.total_usage.total * 100 if a.total_usage.total > 0 else 0
        print(f"  {GREEN}✓ B used {abs(delta_t):,} fewer tokens ({pct:.0f}% reduction){RESET}")
    elif delta_t > 0:
        pct = delta_t / a.total_usage.total * 100 if a.total_usage.total > 0 else 0
        print(f"  {RED}✗ B used {delta_t:,} more tokens ({pct:.0f}% increase){RESET}")
    else:
        print(f"  {DIM}Token usage identical{RESET}")

    if delta_f < 0:
        print(f"  {GREEN}✓ B loaded {abs(delta_f)} fewer context file(s){RESET}")
    elif delta_f > 0:
        print(f"  {YELLOW}✗ B loaded {delta_f} more context file(s){RESET}")
    else:
        print(f"  {DIM}Same number of context files{RESET}")

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

  water [PROJECT] [--optimist]
      Estimate water consumption equivalent for your token usage.
      Default: ~22,500 gal / 1B tokens (Li et al. 2023, conservative baseline).
      --optimist: ~6,000 gal / 1B tokens (H100-era efficient infra, lower bound).

  report [PROJECT]
      Generate a self-contained HTML report — shareable with your team.
      Includes session timeline, top files, water impact, and recommendations.

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
  agentrace report
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
        optimist = "--optimist" in rest
        remaining = [r for r in rest if r != "--optimist"]
        project, _ = _resolve_project(remaining)
        _cmd_water.run(project, optimist=optimist)

    elif cmd == "report":
        project, _ = _resolve_project(rest)
        _cmd_report.run(project)

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: projects, sessions, show, stats, compare, files, watch, recommend, diff, water, report")


if __name__ == "__main__":
    main()
