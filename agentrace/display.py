"""
display.py — Shared display helpers: colors, bars, spinners, boxes.
"""

import sys
import time
import itertools
from pathlib import Path

# ── ANSI ──────────────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
PURPLE = "\033[35m"
WHITE  = "\033[37m"
ORANGE = "\033[38;5;208m"
GOLD   = "\033[38;5;220m"
TEAL   = "\033[38;5;73m"
MUTED  = "\033[38;5;244m"

def short(path: str) -> str:
    home = str(Path.home())
    return ("~" + path[len(home):]) if path.startswith(home) else path

def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)

# ── Bars ──────────────────────────────────────────────────────────────────────

def color_bar(fraction: float, width: int = 28) -> str:
    """
    Colored block bar. Color encodes cost level:
      green  → cheap  (< 33%)
      yellow → medium (33–66%)
      red    → expensive (> 66%)
    """
    filled = max(1, round(fraction * width))
    if fraction > 0.66:
        color = RED
    elif fraction > 0.33:
        color = YELLOW
    else:
        color = GREEN
    bar = "█" * filled + DIM + "░" * (width - filled) + RESET
    return f"{color}{bar}{RESET}"

def mini_bar(fraction: float, width: int = 20) -> str:
    """Simple cyan bar, no color gradient."""
    filled = max(0, round(fraction * width))
    return CYAN + "█" * filled + DIM + "░" * (width - filled) + RESET

# ── Spinner ───────────────────────────────────────────────────────────────────

class Spinner:
    """
    Context manager for a terminal spinner.

        with Spinner("Analyzing files"):
            do_work()

    Clears itself when done.
    """
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str = "Working"):
        self.label = label
        self._iter = itertools.cycle(self.FRAMES)
        self._active = False

    def __enter__(self):
        self._active = True
        self._spin()
        return self

    def _spin(self):
        import threading
        def _loop():
            while self._active:
                frame = next(self._iter)
                sys.stdout.write(f"\r  {CYAN}{frame}{RESET}  {DIM}{self.label}…{RESET}")
                sys.stdout.flush()
                time.sleep(0.08)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def __exit__(self, *_):
        self._active = False
        time.sleep(0.1)
        sys.stdout.write("\r" + " " * (len(self.label) + 12) + "\r")
        sys.stdout.flush()

# ── Box / section headers ─────────────────────────────────────────────────────

def _strip_ansi(s: str) -> str:
    """Strip ANSI escape codes for measuring visual width."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)

def box(title: str, subtitle: str = "", width: int = 0) -> str:
    """
    Render a rounded box header. Width auto-sizes to content if width=0.
    Min width 44, max width 72.
    """
    # Measure visual widths (ANSI-stripped)
    t_vis = len(_strip_ansi(title))
    s_vis = len(_strip_ansi(subtitle)) if subtitle else 0
    content_w = max(t_vis, s_vis)
    inner = max(44, min(72, content_w + 4)) if not width else (width - 2)

    top    = f"  ╭{'─' * inner}╮"
    t_line = f"  │  {BOLD}{title}{RESET}" + " " * max(0, inner - 2 - t_vis) + "│"

    if subtitle:
        s_line = f"  │  {DIM}{subtitle}{RESET}" + " " * max(0, inner - 2 - s_vis) + "│"
        bottom = f"  ╰{'─' * inner}╯"
        return f"{top}\n{t_line}\n{s_line}\n{bottom}"

    bottom = f"  ╰{'─' * inner}╯"
    return f"{top}\n{t_line}\n{bottom}"

def section(title: str) -> str:
    return f"\n  {BOLD}{title}{RESET}\n"

def rule(width: int = 60) -> str:
    return f"  {DIM}{'─' * width}{RESET}"
