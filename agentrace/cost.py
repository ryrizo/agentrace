"""
cost.py — Token cost estimation and $ pricing for Claude models.
"""

from pathlib import Path
from .parser import Session

# Pricing per million tokens (as of early 2025)
# Format: (input_fresh, cache_read, cache_write, output)
_PRICING: dict[str, tuple[float, float, float, float]] = {
    "opus":    (15.00, 1.50, 3.75, 75.00),
    "sonnet":  ( 3.00, 0.30, 0.375, 15.00),
    "haiku":   ( 0.80, 0.08, 0.20,   4.00),
}

def _model_key(model: str | None) -> str:
    if not model:
        return "sonnet"
    m = model.lower()
    if "opus" in m:
        return "opus"
    if "haiku" in m:
        return "haiku"
    return "sonnet"

def session_cost(s: Session) -> float:
    """Estimate $ cost of a session."""
    key = _model_key(s.model)
    p_in, p_cr, p_cw, p_out = _PRICING[key]
    cost = (
        s.usage.input_tokens         / 1_000_000 * p_in +
        s.usage.cache_read_tokens    / 1_000_000 * p_cr +
        s.usage.cache_creation_tokens/ 1_000_000 * p_cw +
        s.usage.output_tokens        / 1_000_000 * p_out
    )
    return cost

def fmt_cost(dollars: float) -> str:
    if dollars < 0.01:
        return f"${dollars*100:.2f}¢"
    return f"${dollars:.3f}"

def estimate_file_tokens(path: str) -> int | None:
    """Estimate token count for a file on disk. Returns None if file not found."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text(errors="replace")
        # Rough heuristic: 1 token ≈ 4 chars for code/text
        return max(1, len(text) // 4)
    except Exception:
        return None
