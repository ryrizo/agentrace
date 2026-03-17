"""
cmd_recommend.py — Context optimization recommendations.

Analyzes session history and suggests which files to:
  - Pin to CLAUDE.md (always load)
  - Load on-demand (rarely used but expensive)
  - Split (large and frequently loaded)
  - Clean up (no longer on disk)
"""

from dataclasses import dataclass
from .parser import load_sessions_sorted
from .cost import estimate_file_tokens, fmt_cost, _model_key, _PRICING
from .display import (
    short, fmt_tokens, color_bar, mini_bar, rule, section, box,
    RESET, BOLD, DIM, GREEN, YELLOW, RED, CYAN, ORANGE, GOLD, MUTED, PURPLE
)


@dataclass
class FileRec:
    path: str
    load_count: int
    total_sessions: int
    tokens_per_load: int | None   # None = not found on disk
    total_spend: int              # tokens_per_load × load_count (0 if unknown)

    @property
    def load_frequency(self) -> float:
        if self.total_sessions == 0:
            return 0.0
        return self.load_count / self.total_sessions


def _analyze(project: str | None) -> tuple[list[FileRec], int]:
    sessions = load_sessions_sorted(project)
    if not sessions:
        return [], 0

    n = len(sessions)
    file_map: dict[str, FileRec] = {}

    for s in sessions:
        for fp in s.unique_files:
            if fp not in file_map:
                tok = estimate_file_tokens(fp)
                file_map[fp] = FileRec(
                    path=fp,
                    load_count=0,
                    total_sessions=n,
                    tokens_per_load=tok,
                    total_spend=0,
                )
            entry = file_map[fp]
            entry.load_count += 1
            if entry.tokens_per_load:
                entry.total_spend = entry.tokens_per_load * entry.load_count

    return list(file_map.values()), n


def run(project: str | None = None):
    from .display import Spinner

    with Spinner("Analyzing session history"):
        files, n_sessions = _analyze(project)

    if not files:
        print("\n  No sessions or context files found.\n")
        return

    scope = short(project) if project else "all projects"

    # ── Categorize ────────────────────────────────────────────────────────────
    always_load: list[FileRec] = []    # 📌 Add to CLAUDE.md
    on_demand:   list[FileRec] = []    # 🎯 Load on-demand
    split:       list[FileRec] = []    # ✂️  Consider splitting
    dead_weight: list[FileRec] = []    # 🗑  Clean up references

    for f in files:
        if f.tokens_per_load is None:
            dead_weight.append(f)
            continue
        freq = f.load_frequency
        tok  = f.tokens_per_load
        # Order matters — a file can match multiple criteria; use priority order
        if freq >= 0.6 and tok <= 8000:
            always_load.append(f)
        elif freq < 0.25 and f.total_spend > 2000:
            on_demand.append(f)
        elif freq >= 0.4 and tok > 8000:
            split.append(f)

    # Sort each category by impact descending
    always_load.sort(key=lambda f: f.load_count, reverse=True)
    on_demand.sort(key=lambda f: f.total_spend, reverse=True)
    split.sort(key=lambda f: f.total_spend, reverse=True)
    dead_weight.sort(key=lambda f: f.load_count, reverse=True)

    print()
    print(box(
        "💡  Context Recommendations",
        f"{n_sessions} sessions  ·  {len(files)} unique files  ·  {scope}"
    ))

    any_recs = any([always_load, on_demand, split, dead_weight])
    if not any_recs:
        print(f"\n  {GREEN}✓ No actionable recommendations — context looks well-optimized!{RESET}\n")
        return

    # ── 📌 Always load ────────────────────────────────────────────────────────
    if always_load:
        print(section("  📌  Add to CLAUDE.md  —  always loaded, small enough to pin"))
        for f in always_load:
            freq_pct = f.load_frequency * 100
            short_path = short(f.path)
            parts = short_path.rsplit("/", 1)
            if len(parts) == 2:
                path_display = f"{DIM}{parts[0]}/{RESET}{BOLD}{parts[1]}{RESET}"
            else:
                path_display = f"{BOLD}{short_path}{RESET}"
            print(f"  {path_display}")
            bar = mini_bar(f.load_frequency, width=20)
            print(
                f"  {bar}  "
                f"{BOLD}{freq_pct:.0f}%{RESET} of sessions  "
                f"{DIM}·  {fmt_tokens(f.tokens_per_load)}/load{RESET}"
            )
            print()

    # ── 🎯 Load on-demand ─────────────────────────────────────────────────────
    if on_demand:
        print(section("  🎯  Load on-demand  —  rarely used but costly when loaded"))
        for f in on_demand:
            freq_pct = f.load_frequency * 100
            short_path = short(f.path)
            parts = short_path.rsplit("/", 1)
            if len(parts) == 2:
                path_display = f"{DIM}{parts[0]}/{RESET}{BOLD}{parts[1]}{RESET}"
            else:
                path_display = f"{BOLD}{short_path}{RESET}"
            print(f"  {path_display}")
            bar = mini_bar(f.load_frequency, width=20)
            print(
                f"  {bar}  "
                f"{BOLD}{freq_pct:.0f}%{RESET} of sessions  "
                f"{DIM}·  {fmt_tokens(f.total_spend)} total tokens wasted{RESET}"
            )
            print()

    # ── ✂️  Consider splitting ─────────────────────────────────────────────────
    if split:
        print(section("  ✂️   Consider splitting  —  large files loaded frequently"))
        for f in split:
            freq_pct = f.load_frequency * 100
            short_path = short(f.path)
            parts = short_path.rsplit("/", 1)
            if len(parts) == 2:
                path_display = f"{DIM}{parts[0]}/{RESET}{BOLD}{parts[1]}{RESET}"
            else:
                path_display = f"{BOLD}{short_path}{RESET}"
            print(f"  {path_display}")
            bar = color_bar(f.load_frequency, width=20)
            print(
                f"  {bar}  "
                f"{BOLD}{freq_pct:.0f}%{RESET} of sessions  "
                f"{DIM}·  {fmt_tokens(f.tokens_per_load)}/load  ·  {fmt_tokens(f.total_spend)} total{RESET}"
            )
            print()

    # ── 🗑  Dead weight ───────────────────────────────────────────────────────
    if dead_weight:
        print(section("  🗑   Clean up references  —  files no longer on disk"))
        for f in dead_weight:
            short_path = short(f.path)
            print(f"  {DIM}{short_path}{RESET}  {DIM}×{f.load_count} loads{RESET}")
        print()

    # ── Savings estimate ──────────────────────────────────────────────────────
    savings_on_demand = sum(f.total_spend for f in on_demand)
    savings_split     = sum(f.total_spend // 2 for f in split)   # ~50% saving if split
    total_savings     = savings_on_demand + savings_split

    print(rule())
    print()
    if total_savings > 0:
        print(f"  {DIM}Estimated token savings{RESET}  {BOLD}{GOLD}{fmt_tokens(total_savings)}{RESET} tokens")
        print(f"  {DIM}  · {fmt_tokens(savings_on_demand)} from making on-demand files opt-in{RESET}")
        if savings_split:
            print(f"  {DIM}  · {fmt_tokens(savings_split)} from splitting large files (~50% estimate){RESET}")
    else:
        print(f"  {DIM}Savings estimate: insufficient data (files not found on disk){RESET}")

    print()
