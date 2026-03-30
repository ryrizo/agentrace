"""
cmd_water.py — Water consumption impact report.

Estimates data center water usage for your Claude Code token consumption,
based on research showing ~22,500 gallons per 1 billion tokens.
"""

from collections import defaultdict
from .parser import load_sessions_sorted
from .display import (
    short, fmt_tokens, mini_bar, box, section, rule, Spinner,
    RESET, BOLD, DIM, CYAN,
)

# ── Constants ─────────────────────────────────────────────────────────────────

GALLONS_PER_BILLION_TOKENS = 22_500

COMPARISONS = [
    ("water bottles",     0.132),    # 500ml
    ("bathtubs",          50.0),
    ("kiddie pools",      100.0),
    ("garden hose minutes", 12.0),
    ("backyard pools",    20_000.0),
]

COMPARISON_EMOJI = {
    "water bottles":       "💧",
    "bathtubs":            "🛁",
    "kiddie pools":        "🏊",
    "garden hose minutes": "🌿",
    "backyard pools":      "🏡",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tokens_to_gallons(tokens: int) -> float:
    return tokens / 1_000_000_000 * GALLONS_PER_BILLION_TOKENS


def _fmt_count(n: float) -> str:
    """Format a comparison count nicely."""
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.1f}"


def _fmt_gallons(g: float) -> str:
    if g >= 1:
        return f"{int(round(g)):,}"
    return f"{g:.2f}"


# ── Main command ──────────────────────────────────────────────────────────────

def run(project: str | None = None):
    with Spinner("Calculating water impact"):
        sessions = load_sessions_sorted(project)

    if not sessions:
        print("\n  No sessions found.\n")
        return

    scope = short(project) if project else "all projects"
    total_tokens = sum(s.total_usage.total for s in sessions)
    total_gallons = _tokens_to_gallons(total_tokens)

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print(box(
        f"🌊  Water Impact  {scope}",
        f"{len(sessions)} sessions  ·  {fmt_tokens(total_tokens)} tokens  ·  est. {_fmt_gallons(total_gallons)} gallons",
    ))

    # ── Equivalents ───────────────────────────────────────────────────────────
    print(section("  Roughly equivalent to"))

    for name, gallons_each in COMPARISONS:
        count = total_gallons / gallons_each
        if count < 0.1 or count > 9999:
            continue
        emoji = COMPARISON_EMOJI.get(name, "💧")
        if count >= 1:
            bar_display = f"{BOLD}{_fmt_count(count):>6}{RESET}"
        else:
            # show as fraction e.g. "1/7"
            bar_display = f"{DIM}{_fmt_count(count):>6}{RESET}"
        print(f"  {emoji}  {bar_display}  {DIM}{name}{RESET}")

    # ── By session ────────────────────────────────────────────────────────────
    print()
    print(rule())
    print(section("  By session  ·  heaviest first"))

    sorted_sessions = sorted(sessions, key=lambda s: s.total_usage.total, reverse=True)
    top_sessions = sorted_sessions[:10]
    max_tokens = top_sessions[0].total_usage.total if top_sessions else 1

    # Build index map for display numbers
    session_idx = {s.session_id: i + 1 for i, s in enumerate(sessions)}

    for s in top_sessions:
        idx = session_idx.get(s.session_id, "?")
        fraction = s.total_usage.total / max_tokens if max_tokens > 0 else 0
        bar = mini_bar(fraction, width=20)
        gallons = _tokens_to_gallons(s.total_usage.total)
        bottles = gallons / 0.132
        print(
            f"  {DIM}#{idx:<3}{RESET}  {DIM}{s.date}{RESET}  {bar}  "
            f"{BOLD}{fmt_tokens(s.total_usage.total):>5}{RESET}  "
            f"{CYAN}{BOLD}{_fmt_gallons(gallons):>3} gal{RESET}  "
            f"{DIM}≈ {int(round(bottles)):,} bottles{RESET}"
        )

    # ── By day (if sessions span >1 day) ─────────────────────────────────────
    dates = {s.date for s in sessions if s.date}
    if len(dates) > 1:
        print()
        print(rule())
        print(section("  By day"))

        day_map: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "gallons": 0.0, "count": 0})
        for s in sessions:
            d = s.date or "unknown"
            day_map[d]["tokens"] += s.total_usage.total
            day_map[d]["gallons"] += _tokens_to_gallons(s.total_usage.total)
            day_map[d]["count"] += 1

        sorted_days = sorted(day_map.items())
        max_day_gallons = max(v["gallons"] for v in day_map.values()) or 1

        for date, stats in sorted_days:
            fraction = stats["gallons"] / max_day_gallons
            bar = mini_bar(fraction, width=20)
            n = stats["count"]
            sessions_label = f"{n} session{'s' if n != 1 else ''}"
            print(
                f"  {DIM}{date}{RESET}  {bar}  "
                f"{CYAN}{BOLD}{_fmt_gallons(stats['gallons']):>3} gal{RESET}  "
                f"{DIM}({fmt_tokens(stats['tokens'])} tokens, {sessions_label}){RESET}"
            )

    # ── Footer ────────────────────────────────────────────────────────────────
    print()
    print(rule())
    print(
        f"\n  {DIM}⚠  Estimate based on ~22,500 gal / 1B tokens (data center cooling research){RESET}"
    )
    print(
        f"  {DIM}   Actual usage varies by provider, region, and cooling method.{RESET}"
    )
    print()
