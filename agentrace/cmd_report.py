"""
cmd_report.py — Generate a self-contained HTML report for agentrace sessions.

Produces a single agentrace-report.html in the current working directory.
No external dependencies — everything inline.
"""

from pathlib import Path
from datetime import date
from .parser import load_sessions_sorted, Session
from .cost import session_cost, fmt_cost, estimate_file_tokens
from .display import Spinner, short

# ── Constants (mirrored from cmd_water.py) ────────────────────────────────────

GALLONS_PER_BILLION_TOKENS = 22_500

COMPARISONS = [
    ("water bottles (500ml)", 0.132),
    ("bathtubs",              50.0),
    ("kiddie pools",          100.0),
    ("garden hose minutes",   12.0),
    ("backyard pools",        20_000.0),
]

COMPARISON_EMOJI = {
    "water bottles (500ml)": "💧",
    "bathtubs":              "🛁",
    "kiddie pools":          "🏊",
    "garden hose minutes":   "🌿",
    "backyard pools":        "🏡",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tokens_to_gallons(tokens: int) -> float:
    return tokens / 1_000_000_000 * GALLONS_PER_BILLION_TOKENS


def _fmt_gallons(g: float) -> str:
    if g >= 1:
        return f"{int(round(g)):,}"
    return f"{g:.3f}"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _fmt_count(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.1f}"


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


# ── SVG bar chart ─────────────────────────────────────────────────────────────

def _svg_sessions_chart(sessions: list, width: int = 800, height: int = 180) -> str:
    """Generate inline SVG with vertical bars per session, colored by token size."""
    if not sessions:
        return f'<svg width="{width}" height="{height}"><text x="20" y="90" fill="#565f89">No session data</text></svg>'

    dated = [s for s in sessions if s.started_at]
    if not dated:
        dated = sessions

    # Sort chronologically
    sorted_sessions = sorted(dated, key=lambda s: (s.started_at or s.date or ""))

    max_tok = max(s.usage.total for s in sorted_sessions) or 1
    n = len(sorted_sessions)

    # Layout
    pad_left = 50
    pad_right = 20
    pad_top = 16
    pad_bottom = 40
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    bar_gap = 2
    bar_w = max(2, (chart_w - bar_gap * (n - 1)) // n) if n > 0 else chart_w

    rects = []
    labels = []

    for i, s in enumerate(sorted_sessions):
        tok = s.usage.total
        fraction = tok / max_tok
        bar_h = max(2, int(fraction * chart_h))
        x = pad_left + i * (bar_w + bar_gap)
        y = pad_top + chart_h - bar_h

        if tok < 500_000:
            color = "#9ece6a"
        elif tok < 2_000_000:
            color = "#e0af68"
        else:
            color = "#f7768e"

        cost = session_cost(s)
        cache_pct = 0
        if s.usage.total_input > 0:
            cache_pct = s.usage.cache_read_tokens / s.usage.total_input * 100
        tooltip = (
            f"{s.slug or s.session_id[:8]} | "
            f"{s.date or '?'} | "
            f"{_fmt_tokens(tok)} tokens | "
            f"{fmt_cost(cost)} | "
            f"cache {cache_pct:.0f}%"
        )

        rects.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" '
            f'fill="{color}" rx="1" class="bar">'
            f'<title>{_escape(tooltip)}</title>'
            f'</rect>'
        )

        # X-axis date label (every few bars if many sessions)
        step = max(1, n // 10)
        if i % step == 0:
            label_x = x + bar_w // 2
            label_date = (s.date or "?")[-5:]  # MM-DD
            labels.append(
                f'<text x="{label_x}" y="{pad_top + chart_h + 16}" '
                f'fill="#565f89" font-size="9" text-anchor="middle">'
                f'{_escape(label_date)}</text>'
            )

    # Y-axis ticks
    y_ticks = []
    for pct, label in [(1.0, _fmt_tokens(max_tok)), (0.5, _fmt_tokens(max_tok // 2)), (0.0, "0")]:
        ty = pad_top + chart_h - int(pct * chart_h)
        y_ticks.append(
            f'<line x1="{pad_left - 4}" y1="{ty}" x2="{pad_left + chart_w}" y2="{ty}" '
            f'stroke="#2a2e47" stroke-width="1"/>'
            f'<text x="{pad_left - 6}" y="{ty + 4}" fill="#565f89" font-size="9" text-anchor="end">'
            f'{_escape(label)}</text>'
        )

    inner = "\n  ".join(y_ticks + rects + labels)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'style="overflow: visible;">\n  {inner}\n</svg>'
    )


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(sessions: list, project_path: str | None) -> str:
    if not sessions:
        scope_label = short(project_path) if project_path else "all projects"
        return f"<html><body>No sessions found for {_escape(scope_label)}</body></html>"

    # ── Aggregate metrics ────────────────────────────────────────────────────
    total_tokens = sum(s.usage.total for s in sessions)
    total_cost   = sum(session_cost(s) for s in sessions)
    total_input  = sum(s.usage.total_input for s in sessions)
    total_cache  = sum(s.usage.cache_read_tokens for s in sessions)
    cache_pct    = (total_cache / total_input * 100) if total_input > 0 else 0.0
    total_gallons = _tokens_to_gallons(total_tokens)

    scope_label = short(project_path) if project_path else "all projects"

    dated = [s for s in sessions if s.started_at or s.date]
    if dated:
        dates = sorted((s.date or s.started_at[:10]) for s in dated)
        date_range = f"{dates[0]} → {dates[-1]}" if len(dates) > 1 and dates[0] != dates[-1] else dates[0]
    else:
        date_range = "—"

    today = date.today().isoformat()

    # ── File analysis ────────────────────────────────────────────────────────
    n_sessions = len(sessions)
    file_counts: dict[str, int] = {}
    file_sessions: dict[str, set] = {}
    for s in sessions:
        for fp in s.unique_files:
            file_counts[fp] = file_counts.get(fp, 0) + 1
            file_sessions.setdefault(fp, set()).add(s.session_id)

    top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Recommendations
    always_load = []
    load_on_demand = []
    for fp, count in file_counts.items():
        freq = count / n_sessions
        tok = estimate_file_tokens(fp)
        if freq > 0.60 and tok is not None and tok < 8_000:
            always_load.append((fp, count, freq, tok))
        elif freq < 0.25:
            load_on_demand.append((fp, count, freq))

    always_load.sort(key=lambda x: x[2], reverse=True)
    load_on_demand.sort(key=lambda x: x[2])

    # ── Hero metric cards ────────────────────────────────────────────────────
    if cache_pct >= 80:
        cache_color = "#9ece6a"
    elif cache_pct >= 50:
        cache_color = "#e0af68"
    else:
        cache_color = "#f7768e"

    hero_cards = f"""
      <div class="hero-grid">
        <div class="card hero-card">
          <div class="hero-label">Total Tokens</div>
          <div class="hero-value" style="color:#7dcfff">{_escape(_fmt_tokens(total_tokens))}</div>
          <div class="hero-sub">{total_tokens:,} tokens across {n_sessions} sessions</div>
        </div>
        <div class="card hero-card">
          <div class="hero-label">Total Cost</div>
          <div class="hero-value" style="color:#e0af68">{_escape(fmt_cost(total_cost))}</div>
          <div class="hero-sub">{_escape(fmt_cost(total_cost / n_sessions))} avg per session</div>
        </div>
        <div class="card hero-card">
          <div class="hero-label">Water Equivalent</div>
          <div class="hero-value" style="color:#2ac3de">{_escape(_fmt_gallons(total_gallons))} gal</div>
          <div class="hero-sub">{_escape(_fmt_gallons(total_gallons / n_sessions))} gal avg per session</div>
        </div>
        <div class="card hero-card">
          <div class="hero-label">Cache Hit Rate</div>
          <div class="hero-value" style="color:{cache_color}">{cache_pct:.0f}%</div>
          <div class="hero-sub">of input tokens served from cache</div>
        </div>
      </div>
    """

    # ── Session chart ────────────────────────────────────────────────────────
    chart_svg = _svg_sessions_chart(sessions)
    chart_section = f"""
      <div class="card section">
        <h2 class="section-title">Sessions Over Time</h2>
        <div class="chart-legend">
          <span class="legend-dot" style="background:#9ece6a"></span> &lt;500k tokens
          <span class="legend-dot" style="background:#e0af68; margin-left:12px"></span> 500k–2M
          <span class="legend-dot" style="background:#f7768e; margin-left:12px"></span> &gt;2M
        </div>
        <div class="chart-wrap">
          {chart_svg}
        </div>
      </div>
    """

    # ── Top context files ────────────────────────────────────────────────────
    max_count = top_files[0][1] if top_files else 1
    file_rows = ""
    for fp, count in top_files:
        short_path = short(fp)
        parts = short_path.rsplit("/", 1)
        if len(parts) == 2:
            dir_part  = _escape(parts[0] + "/")
            file_part = _escape(parts[1])
        else:
            dir_part  = ""
            file_part = _escape(short_path)
        tok = estimate_file_tokens(fp)
        tok_str = _fmt_tokens(tok) if tok else "?"
        bar_pct = count / max_count * 100
        file_rows += f"""
        <div class="file-row">
          <div class="file-label">
            <span class="file-dir">{dir_part}</span><span class="file-name">{file_part}</span>
          </div>
          <div class="file-bar-wrap">
            <div class="file-bar" style="width:{bar_pct:.1f}%"></div>
          </div>
          <div class="file-meta">
            <span class="file-count">{count}×</span>
            <span class="file-tokens muted">~{tok_str} tok</span>
          </div>
        </div>"""

    files_section = f"""
      <div class="card section">
        <h2 class="section-title">Top Context Files</h2>
        <div class="files-list">{file_rows}
        </div>
      </div>
    """ if top_files else ""

    # ── Water impact ─────────────────────────────────────────────────────────
    comparison_rows = ""
    for name, gallons_each in COMPARISONS:
        count = total_gallons / gallons_each
        if count < 0.05 or count > 99_999:
            continue
        emoji = COMPARISON_EMOJI.get(name, "💧")
        comparison_rows += f"""
          <div class="water-row">
            <span class="water-emoji">{emoji}</span>
            <span class="water-count">{_escape(_fmt_count(count))}</span>
            <span class="water-label muted">{_escape(name)}</span>
          </div>"""

    water_section = f"""
      <div class="card section water-card">
        <h2 class="section-title">🌊 Water Impact</h2>
        <p class="water-total">
          <span style="color:#2ac3de;font-size:2em;font-weight:700">{_escape(_fmt_gallons(total_gallons))}</span>
          <span class="muted" style="font-size:1.1em"> gallons estimated</span>
        </p>
        <div class="water-comparisons">{comparison_rows}
        </div>
        <p class="muted water-disclaimer">
          Based on ~22,500 gal / 1B tokens (data center cooling research). Actual usage varies.
        </p>
      </div>
    """

    # ── Recommendations ───────────────────────────────────────────────────────
    rec_html = ""
    if always_load or load_on_demand:
        always_items = ""
        for fp, count, freq, tok in always_load[:8]:
            short_path = _escape(short(fp))
            always_items += f'<li><span class="rec-file">{short_path}</span> <span class="muted">({freq*100:.0f}% of sessions, ~{_fmt_tokens(tok)} tok)</span></li>\n'

        demand_items = ""
        for fp, count, freq in load_on_demand[:8]:
            short_path = _escape(short(fp))
            demand_items += f'<li><span class="rec-file">{short_path}</span> <span class="muted">({freq*100:.0f}% of sessions)</span></li>\n'

        always_block = f"""
          <div class="rec-group">
            <h3 class="rec-subtitle">📌 Always load <span class="muted">(pin in CLAUDE.md)</span></h3>
            <ul class="rec-list">{always_items}</ul>
          </div>
        """ if always_items else ""

        demand_block = f"""
          <div class="rec-group">
            <h3 class="rec-subtitle">📂 Load on-demand <span class="muted">(skip from CLAUDE.md)</span></h3>
            <ul class="rec-list">{demand_items}</ul>
          </div>
        """ if demand_items else ""

        rec_html = f"""
      <div class="card section">
        <h2 class="section-title">Recommendations</h2>
        {always_block}
        {demand_block}
      </div>
        """

    # ── CSS ───────────────────────────────────────────────────────────────────
    css = """
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

      body {
        background: #1a1b26;
        color: #c0caf5;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", monospace;
        font-size: 14px;
        line-height: 1.6;
        padding: 32px 24px 64px;
        max-width: 1100px;
        margin: 0 auto;
      }

      /* Header */
      .report-header { margin-bottom: 32px; }
      .report-title {
        font-size: 2em;
        font-weight: 700;
        color: #c0caf5;
        letter-spacing: -0.5px;
      }
      .report-title span { color: #7dcfff; }
      .report-subtitle { color: #565f89; margin-top: 4px; font-size: 0.9em; }

      /* Cards */
      .card {
        background: #24283b;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 20px;
        border: 1px solid #2a2e47;
      }

      /* Hero grid */
      .hero-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 20px;
      }
      @media (max-width: 700px) {
        .hero-grid { grid-template-columns: repeat(2, 1fr); }
      }
      .hero-card { text-align: center; padding: 20px 16px; }
      .hero-label { font-size: 0.75em; text-transform: uppercase; letter-spacing: 1px; color: #565f89; margin-bottom: 8px; }
      .hero-value { font-size: 2.2em; font-weight: 700; line-height: 1; }
      .hero-sub { font-size: 0.75em; color: #565f89; margin-top: 6px; }

      /* Section titles */
      .section-title {
        font-size: 1em;
        font-weight: 600;
        color: #c0caf5;
        margin-bottom: 16px;
        padding-bottom: 10px;
        border-bottom: 1px solid #2a2e47;
        letter-spacing: 0.3px;
      }

      /* Chart */
      .chart-legend { font-size: 0.8em; color: #565f89; margin-bottom: 12px; }
      .legend-dot {
        display: inline-block;
        width: 10px; height: 10px;
        border-radius: 2px;
        vertical-align: middle;
        margin-right: 4px;
      }
      .chart-wrap { width: 100%; overflow: hidden; }
      .bar { transition: opacity 0.1s; cursor: default; }
      .bar:hover { opacity: 0.8; }

      /* Files */
      .files-list { display: flex; flex-direction: column; gap: 10px; }
      .file-row { display: grid; grid-template-columns: 1fr 160px 90px; align-items: center; gap: 12px; }
      .file-label { font-size: 0.85em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .file-dir { color: #565f89; }
      .file-name { font-weight: 600; color: #c0caf5; }
      .file-bar-wrap { background: #1a1b26; border-radius: 4px; height: 8px; overflow: hidden; }
      .file-bar { background: #7dcfff; height: 100%; border-radius: 4px; min-width: 2px; }
      .file-meta { display: flex; gap: 8px; font-size: 0.8em; white-space: nowrap; }
      .file-count { color: #9ece6a; font-weight: 600; }
      .file-tokens { }

      /* Water */
      .water-card { background: #1f2335; border-color: #2ac3de33; }
      .water-total { margin-bottom: 16px; }
      .water-comparisons { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
      .water-row { display: flex; align-items: center; gap: 10px; font-size: 0.9em; }
      .water-emoji { font-size: 1.2em; width: 24px; text-align: center; }
      .water-count { font-weight: 700; color: #c0caf5; min-width: 60px; }
      .water-label { }
      .water-disclaimer { font-size: 0.78em; margin-top: 12px; }

      /* Recommendations */
      .rec-group { margin-bottom: 20px; }
      .rec-group:last-child { margin-bottom: 0; }
      .rec-subtitle { font-size: 0.9em; font-weight: 600; color: #c0caf5; margin-bottom: 10px; }
      .rec-list { list-style: none; display: flex; flex-direction: column; gap: 6px; padding-left: 8px; }
      .rec-list li::before { content: "→ "; color: #565f89; }
      .rec-file { font-family: monospace; font-size: 0.85em; color: #7dcfff; }

      /* Shared */
      .muted { color: #565f89; }

      /* Footer */
      .report-footer {
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid #2a2e47;
        font-size: 0.8em;
        color: #565f89;
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .footer-link { color: #7dcfff; text-decoration: none; }
      .footer-link:hover { text-decoration: underline; }
    """

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agentrace Report — {_escape(scope_label)}</title>
  <style>
{css}
  </style>
</head>
<body>
  <div class="report-header">
    <h1 class="report-title"><span>⬡</span> Agentrace Report</h1>
    <p class="report-subtitle">{_escape(scope_label)} · {_escape(date_range)} · Generated {today}</p>
  </div>

  {hero_cards}
  {chart_section}
  {files_section}
  {water_section}
  {rec_html}

  <footer class="report-footer">
    <div>Generated by <a class="footer-link" href="https://github.com/ryrizo/agentrace">agentrace</a> · <a class="footer-link" href="https://github.com/ryrizo/agentrace">github.com/ryrizo/agentrace</a></div>
    <div class="muted">Water estimate based on ~22,500 gal / 1B tokens (data center cooling research). Actual usage varies by provider, region, and cooling method.</div>
  </footer>
</body>
</html>"""

    return html


# ── Entry point ───────────────────────────────────────────────────────────────

def run(project: str | None = None):
    with Spinner("Generating report"):
        sessions = load_sessions_sorted(project)
        html = _build_html(sessions, project)

    out = Path.cwd() / "agentrace-report.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n  ✓ Report written to {out.name}")
    print(f"  open {out.name}\n")
