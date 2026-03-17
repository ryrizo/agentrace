"""
cmd_tree.py — Context tree analysis and CLAUDE.md skeleton generator.

Analyzes which files are loaded together across sessions (co-load clustering),
surfaces the natural context groups, and optionally generates a CLAUDE.md
index skeleton that encodes the tree.

The pattern:
    CLAUDE.md  (tiny index, always loads)
      ├── Backend work?   → load these files
      ├── Frontend work?  → load these files
      └── ...

Result: agents load 2-3 files instead of 8+ per session.
"""

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .parser import load_sessions_sorted, Session
from .cost import estimate_file_tokens
from .display import (
    box, section, rule, mini_bar, short, fmt_tokens,
    RESET, BOLD, DIM, GREEN, YELLOW, RED, CYAN, ORANGE, MUTED, PURPLE,
    Spinner,
)


# ── Cluster detection ─────────────────────────────────────────────────────────

@dataclass
class Cluster:
    files: list[str]
    session_count: int
    total_sessions: int
    name: str = ""

    @property
    def frequency(self) -> float:
        return self.session_count / self.total_sessions if self.total_sessions else 0


def _infer_cluster_name(files: list[str]) -> str:
    """Guess a human name for a cluster based on common path patterns."""
    known = {
        "app/api":      "Backend API",
        "app/engine":   "Capacity Engine",
        "app/models":   "Data Models",
        "app/alembic":  "Migrations",
        "frontend/src/components": "UI Components",
        "frontend/src/views":      "UI Views",
        "frontend/src/hooks":      "Frontend Hooks",
        "frontend/src":            "Frontend",
        "docs":                    "Documentation",
        "tests":                   "Tests",
    }
    # Count hits per known prefix
    scores: dict[str, int] = defaultdict(int)
    for fp in files:
        for prefix, label in known.items():
            if prefix in fp:
                scores[label] += 1
    if scores:
        return max(scores, key=lambda k: scores[k])
    # Fall back to common directory prefix
    dirs = [Path(f).parent.name for f in files]
    common = max(set(dirs), key=dirs.count)
    return common.replace("_", " ").replace("-", " ").title()


def _cluster_sessions(sessions: list[Session], threshold_pct: float = 0.2) -> tuple[
    list[Cluster], list[str], list[str]
]:
    """
    Find co-load clusters using co-occurrence graph + BFS connected components.

    Returns: (clusters, always_load_files, on_demand_files)
    """
    n = len(sessions)
    threshold = max(1, round(n * threshold_pct))

    # Count how often each file appears
    file_counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        for fp in s.unique_files:
            file_counts[fp] += 1

    # Build co-occurrence counts
    co_occur: dict[tuple[str, str], int] = defaultdict(int)
    for s in sessions:
        files = s.unique_files
        for i, a in enumerate(files):
            for b in files[i + 1:]:
                key = (min(a, b), max(a, b))
                co_occur[key] += 1

    # Build adjacency list (only pairs co-occurring >= threshold)
    graph: dict[str, set[str]] = defaultdict(set)
    for (a, b), count in co_occur.items():
        if count >= threshold:
            graph[a].add(b)
            graph[b].add(a)

    # BFS connected components
    visited: set[str] = set()
    raw_clusters: list[list[str]] = []
    all_files = list(file_counts.keys())

    for fp in all_files:
        if fp in visited or fp not in graph:
            continue
        cluster = []
        queue = [fp]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(cluster) >= 2:
            # Sort by file_count descending within cluster
            cluster.sort(key=lambda f: file_counts[f], reverse=True)
            raw_clusters.append(cluster)

    # Sort clusters by how often they collectively appear
    def cluster_session_count(cluster: list[str]) -> int:
        return sum(
            1 for s in sessions
            if any(fp in s.unique_files for fp in cluster)
        )

    clusters = []
    for c in sorted(raw_clusters, key=cluster_session_count, reverse=True):
        sc = cluster_session_count(c)
        clusters.append(Cluster(
            files=c,
            session_count=sc,
            total_sessions=n,
            name=_infer_cluster_name(c),
        ))

    # Always-load: files in >= 70% of sessions, not already in a cluster
    clustered = {fp for c in clusters for fp in c.files}
    always_load = [
        fp for fp, cnt in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        if cnt / n >= 0.7 and fp not in clustered
    ]

    # On-demand: files not clustered, not always-load, and loaded < 2 sessions
    on_demand = [
        fp for fp, cnt in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        if fp not in clustered and fp not in always_load and cnt <= 2
    ]

    return clusters, always_load, on_demand


# ── CLAUDE.md generator ───────────────────────────────────────────────────────

def _generate_claude_md(
    clusters: list[Cluster],
    always_load: list[str],
    on_demand: list[str],
    project_path: str,
) -> str:
    project_name = Path(project_path).name if project_path else "this project"
    lines = [
        f"# CLAUDE.md — Context Index",
        f"",
        f"Read this file first. Then load additional context based on your task.",
        f"Keeping context lean reduces token cost and improves cache efficiency.",
        f"",
    ]

    if always_load:
        lines += ["## Always load\n"]
        for fp in always_load:
            tok = estimate_file_tokens(fp)
            tok_str = f"  (~{fmt_tokens(tok)} tokens)" if tok else ""
            rel = fp.replace(project_path + "/", "") if project_path in fp else short(fp)
            lines.append(f"- {rel}{tok_str}")
        lines.append("")

    lines += ["## Load by task\n"]

    for c in clusters:
        lines.append(f"### {c.name}\n")
        for fp in c.files[:6]:  # cap at 6 per cluster
            rel = fp.replace(project_path + "/", "") if project_path in fp else short(fp)
            tok = estimate_file_tokens(fp)
            tok_str = f"  # ~{fmt_tokens(tok)} tokens" if tok else ""
            lines.append(f"- {rel}{tok_str}")
        lines.append("")

    if on_demand:
        lines += [
            "## On-demand only\n",
            "Load these explicitly when needed — don't pre-load them:\n",
        ]
        for fp in on_demand[:8]:
            rel = fp.replace(project_path + "/", "") if project_path in fp else short(fp)
            lines.append(f"- {rel}")
        lines.append("")

    lines += [
        "---",
        "",
        f"*Generated by [agentrace](https://github.com/ryrizo/agentrace) "
        f"from {len(clusters)} session clusters*",
    ]
    return "\n".join(lines)


# ── Savings estimate ──────────────────────────────────────────────────────────

def _estimate_savings(
    sessions: list[Session],
    clusters: list[Cluster],
    always_load: list[str],
) -> tuple[int, int]:
    """
    Rough estimate of tokens saved per session if the tree is adopted.
    Returns (tokens_saved_per_session, total_saved_across_sessions).
    """
    # Files that would still be loaded per session with the tree:
    # - always_load files (always)
    # - ONE cluster's worth of files (the relevant one)
    # Without tree: avg files per session currently
    current_avg = sum(len(s.unique_files) for s in sessions) / len(sessions) if sessions else 0

    # Estimate files with tree: always_load + avg cluster size
    avg_cluster_size = (
        sum(len(c.files) for c in clusters) / len(clusters)
        if clusters else 0
    )
    tree_avg = len(always_load) + avg_cluster_size

    reduction = max(0, current_avg - tree_avg)

    # Average tokens per file (rough)
    all_files = list({fp for s in sessions for fp in s.unique_files})
    token_estimates = [t for fp in all_files if (t := estimate_file_tokens(fp))]
    avg_tok_per_file = int(sum(token_estimates) / len(token_estimates)) if token_estimates else 2000

    saved_per_session = int(reduction * avg_tok_per_file)
    saved_total = saved_per_session * len(sessions)
    return saved_per_session, saved_total


# ── Main command ──────────────────────────────────────────────────────────────

def run(project: str | None = None):
    from .cost import session_cost, fmt_cost

    with Spinner("Analyzing co-load patterns"):
        sessions = load_sessions_sorted(project)
        if not sessions:
            print("\n  No sessions found.\n")
            return

        clusters, always_load, on_demand = _cluster_sessions(sessions)
        savings_per, savings_total = _estimate_savings(sessions, clusters, always_load)

    project_path = project or (sessions[0].cwd if sessions else "")
    scope = short(project_path) if project_path else "all projects"
    all_file_count = len({fp for s in sessions for fp in s.unique_files})

    print()
    print(box(
        f"🌳  Context Tree  {scope}",
        f"{len(sessions)} sessions  ·  {all_file_count} unique files  ·  {len(clusters)} clusters detected",
    ))

    if not clusters and not always_load:
        print(f"\n  {DIM}Not enough sessions to detect clusters yet.")
        print(f"  Run a few more Claude Code sessions to build a pattern.{RESET}\n")
        return

    current_avg_files = sum(len(s.unique_files) for s in sessions) / len(sessions)

    # ── Always load ────────────────────────────────────────────────────────
    if always_load:
        print(section(f"  📌  Always load  ·  {GREEN}appears in 70%+ of sessions{RESET}"))
        for fp in always_load:
            tok = estimate_file_tokens(fp)
            tok_str = f"  {DIM}~{fmt_tokens(tok)} tokens{RESET}" if tok else ""
            parts = short(fp).rsplit("/", 1)
            display = f"{DIM}{parts[0]}/{RESET}{BOLD}{parts[1]}{RESET}" if len(parts) == 2 else f"{BOLD}{short(fp)}{RESET}"
            print(f"    {display}{tok_str}")
        print()

    # ── Clusters ───────────────────────────────────────────────────────────
    for i, c in enumerate(clusters):
        freq_str = f"{c.session_count}/{c.total_sessions} sessions"
        freq_color = GREEN if c.frequency >= 0.5 else YELLOW
        print(f"  {BOLD}Cluster {i+1}  {c.name}{RESET}  ·  {freq_color}{freq_str}{RESET}\n")

        max_count = max(
            sum(1 for s in sessions if fp in s.unique_files) for fp in c.files
        ) or 1

        for fp in c.files[:6]:
            count = sum(1 for s in sessions if fp in s.unique_files)
            fraction = count / max_count
            bar = mini_bar(fraction, width=18)
            tok = estimate_file_tokens(fp)
            tok_str = f"  {DIM}~{fmt_tokens(tok)}{RESET}" if tok else ""
            parts = short(fp).rsplit("/", 1)
            name = parts[1] if len(parts) == 2 else short(fp)
            dir_  = f"{DIM}{parts[0]}/{RESET}" if len(parts) == 2 else ""
            print(f"    {bar}  {dir_}{BOLD}{name}{RESET}{tok_str}")

        if len(c.files) > 6:
            print(f"    {DIM}… and {len(c.files) - 6} more{RESET}")
        print()

    # ── On-demand ──────────────────────────────────────────────────────────
    if on_demand:
        names = "  ".join(
            Path(fp).name for fp in on_demand[:6]
        )
        more = f"  {DIM}+{len(on_demand)-6} more{RESET}" if len(on_demand) > 6 else ""
        print(f"  {DIM}🎯  On-demand only  ·  rarely loaded{RESET}")
        print(f"    {DIM}{names}{more}{RESET}\n")

    # ── Savings ────────────────────────────────────────────────────────────
    print(rule())

    tree_avg_files = len(always_load) + (
        sum(len(c.files) for c in clusters) / len(clusters) if clusters else 0
    )

    print(f"\n  {DIM}Current avg files/session{RESET}  {BOLD}{current_avg_files:.1f}{RESET}")

    if tree_avg_files < current_avg_files and savings_per > 0:
        print(f"  {DIM}Estimated with tree{RESET}       {BOLD}{GREEN}{tree_avg_files:.1f}{RESET}  {DIM}(↓ {current_avg_files - tree_avg_files:.1f} fewer){RESET}")
        print(f"\n  ✨ Applying this tree could save ~{BOLD}{fmt_tokens(savings_per)}{RESET} tokens/session")
    elif len(clusters) <= 1:
        print(f"\n  {DIM}💡 Run more varied sessions to reveal distinct clusters.{RESET}")
        print(f"  {DIM}   With 3+ clusters, the tree will show clear loading lanes.{RESET}")

    # ── Generate CLAUDE.md ─────────────────────────────────────────────────
    print()
    try:
        answer = input(f"  → Write CLAUDE.md skeleton to {CYAN}CLAUDE.md.suggested{RESET}? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if answer == "y":
        content = _generate_claude_md(clusters, always_load, on_demand, project_path)
        out_path = Path(project_path) / "CLAUDE.md.suggested" if project_path else Path("CLAUDE.md.suggested")
        out_path.write_text(content)
        print(f"\n  {GREEN}✓{RESET}  Written to {BOLD}{short(str(out_path))}{RESET}")
        print(f"  {DIM}Review it, then rename to CLAUDE.md when ready.{RESET}\n")
    else:
        print(f"  {DIM}No file written. Run again anytime.{RESET}\n")
