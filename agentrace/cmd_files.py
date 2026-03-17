"""
cmd_files.py — Context file cost analysis.

Shows every file loaded across sessions, ranked by total token spend,
with estimated cost in $ and a visual bar.
"""

from dataclasses import dataclass
from .parser import load_sessions_sorted, Session
from .cost import estimate_file_tokens, session_cost, fmt_cost, _model_key, _PRICING
from .display import (
    short, fmt_tokens, color_bar, rule, section, box,
    RESET, BOLD, DIM, GREEN, YELLOW, RED, CYAN, ORANGE, GOLD, MUTED, PURPLE
)


@dataclass
class FileStats:
    path: str
    load_count: int
    tokens_per_load: int | None   # estimated from disk
    total_token_spend: int        # tokens_per_load × load_count (or 0 if unknown)
    sessions: list[str]           # session IDs that loaded this file


def analyze_files(project: str | None = None) -> tuple[list[FileStats], list[Session]]:
    sessions = load_sessions_sorted(project)
    file_map: dict[str, FileStats] = {}

    for s in sessions:
        for fp in s.unique_files:
            if fp not in file_map:
                tok = estimate_file_tokens(fp)
                file_map[fp] = FileStats(
                    path=fp,
                    load_count=0,
                    tokens_per_load=tok,
                    total_token_spend=0,
                    sessions=[],
                )
            entry = file_map[fp]
            entry.load_count += 1
            entry.sessions.append(s.session_id[:8])
            if entry.tokens_per_load:
                entry.total_token_spend = entry.tokens_per_load * entry.load_count

    ranked = sorted(file_map.values(), key=lambda f: f.total_token_spend, reverse=True)
    return ranked, sessions


def run(project: str | None = None):
    from .display import Spinner

    with Spinner("Analyzing context files"):
        files, sessions = analyze_files(project)

    if not sessions:
        print("\n  No sessions found.\n")
        return

    scope = short(project) if project else "all projects"
    total_loads = sum(f.load_count for f in files)
    total_spend = sum(f.total_token_spend for f in files)
    total_session_cost = sum(session_cost(s) for s in sessions)

    print()
    print(box(
        f"📊  Context File Analysis",
        f"{len(sessions)} sessions  ·  {total_loads} total loads  ·  {len(files)} unique files",
    ))

    if not files:
        print("\n  No context files found in sessions.\n")
        return

    max_spend = max(f.total_token_spend for f in files) or 1
    n_sessions = len(sessions)

    # Separate found vs missing
    found = [f for f in files if f.tokens_per_load is not None]
    missing = [f for f in files if f.tokens_per_load is None]
    display = found[:20]
    hidden = found[20:]

    print(section("  Ranked by total token spend"))

    for i, f in enumerate(display):
        fraction = f.total_token_spend / max_spend
        bar = color_bar(fraction, width=24)

        # File label with heat indicator
        freq = f.load_count / n_sessions
        if freq >= 0.8:
            heat = f"  {RED}🔥 hot{RESET}"
        elif freq >= 0.5:
            heat = f"  {YELLOW}◈ frequent{RESET}"
        else:
            heat = ""

        short_path = short(f.path)
        # Split path into dir + filename for emphasis
        parts = short_path.rsplit("/", 1)
        if len(parts) == 2:
            path_display = f"{DIM}{parts[0]}/{RESET}{BOLD}{parts[1]}{RESET}"
        else:
            path_display = f"{BOLD}{short_path}{RESET}"

        print(f"  {path_display}{heat}")
        print(f"  {bar}  ", end="")

        if f.tokens_per_load:
            spend_color = RED if fraction > 0.66 else (YELLOW if fraction > 0.33 else GREEN)
            print(
                f"{spend_color}{BOLD}{fmt_tokens(f.total_token_spend)}{RESET} tokens  "
                f"{DIM}({fmt_tokens(f.tokens_per_load)}/load × {f.load_count}){RESET}",
                end=""
            )
        else:
            print(f"{DIM}file not found on disk  ×{f.load_count} loads{RESET}", end="")

        print()
        print()  # breathing room

    if hidden:
        print(f"  {DIM}… and {len(hidden)} more smaller files{RESET}\n")
    if missing:
        names = ", ".join(short(f.path).rsplit("/", 1)[-1] for f in missing[:4])
        more = f" +{len(missing)-4} more" if len(missing) > 4 else ""
        print(f"  {DIM}🗂  {len(missing)} file(s) no longer on disk (old refactors): {names}{more}{RESET}\n")

    print(rule())
    print(f"\n  {DIM}Total file token spend{RESET}   {BOLD}{fmt_tokens(total_spend)}{RESET} tokens")
    print(f"  {DIM}Total session cost{RESET}       {BOLD}{GOLD}{fmt_cost(total_session_cost)}{RESET}")

    # Top file callout
    if files and files[0].total_token_spend > 0 and total_spend > 0:
        top = files[0]
        pct = top.total_token_spend / total_spend * 100
        if pct >= 15:
            print(f"\n  💡 {BOLD}{short(top.path).rsplit('/', 1)[-1]}{RESET} accounts for "
                  f"{BOLD}{pct:.0f}%{RESET} of total file spend")

    # Hot files tip
    hot = [f for f in files if f.load_count / n_sessions >= 0.7]
    if hot:
        names = ", ".join(f"{BOLD}{short(f.path).rsplit('/', 1)[-1]}{RESET}" for f in hot[:3])
        print(f"\n  🔥 {names} {'is' if len(hot) == 1 else 'are'} loaded in "
              f"{BOLD}{hot[0].load_count / n_sessions * 100:.0f}%{RESET} of sessions "
              f"— prime candidates for CLAUDE.md")

    print()
