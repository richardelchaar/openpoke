"""Draws the two charts in the report from the saved runs. No model calls, no plotting library.

    python -m evals.charts        writes docs/agent-overload/img/*.svg
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from .report import collect

OUT = Path(__file__).resolve().parent.parent / "docs" / "agent-overload" / "img"
GREY, BLUE = "#8a8f98", "#2563eb"
FONT = 'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif"'


def svg(width: int, height: int, body: List[str], title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{title}">\n<rect width="{width}" height="{height}" fill="white"/>\n'
            + "\n".join(body) + "\n</svg>\n")


def text(x: float, y: float, s: str, size: int = 13, anchor: str = "start", colour: str = "#1f2933", weight: str = "400") -> str:
    return f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" text-anchor="{anchor}" fill="{colour}" font-weight="{weight}" {FONT}>{s}</text>'


def tokens_chart(data: Dict[str, dict], winner: str) -> str:
    """Tokens per message against roster size: the original grows, the lookup doesn't."""
    width, height, left, right, top, bottom = 640, 360, 70, 150, 50, 50
    sizes = [20, 160, 640]
    xs = {s: left + i * (width - left - right) / (len(sizes) - 1) for i, s in enumerate(sizes)}
    top_value = 45000
    y = lambda v: height - bottom - v / top_value * (height - top - bottom)  # noqa: E731
    body = [text(left, 26, "Tokens per message, by roster size", 16, weight="600")]
    for v in range(0, top_value + 1, 10000):
        body.append(f'<line x1="{left}" x2="{width - right}" y1="{y(v):.0f}" y2="{y(v):.0f}" stroke="#e5e7eb"/>')
        body.append(text(left - 8, y(v) + 4, f"{v:,}", 11, "end", "#6b7280"))
    for s in sizes:
        body.append(text(xs[s], height - bottom + 20, f"{s} agents", 12, "middle", "#6b7280"))
    for version, colour, label in (("v0", GREY, "Original"), (winner, BLUE, "Records and lookup")):
        points = [(xs[s], y(data[version][str(s)]["tokens_per_case"])) for s in sizes]
        body.append(f'<polyline fill="none" stroke="{colour}" stroke-width="3" points="' + " ".join(f"{a:.0f},{b:.0f}" for a, b in points) + '"/>')
        for (a, b), s in zip(points, sizes):
            body.append(f'<circle cx="{a:.0f}" cy="{b:.0f}" r="4.5" fill="{colour}"/>')
            above = version == "v0"   # the two lines start close together, so label one above and one below
            body.append(text(a, b - 10 if above else b + 20, f"{data[version][str(s)]['tokens_per_case']:,.0f}", 11, "middle", colour))
        body.append(text(points[-1][0] + 12, points[-1][1] + 4, label, 13, colour=colour, weight="600"))
    return svg(width, height, body, "Tokens per message by roster size")


def outcomes_chart(data: Dict[str, dict], winner: str, world: str, roster: str = "160") -> str:
    """What happened to every message: right, and each way of being wrong."""
    parts: List[Tuple[str, str, List[str]]] = [
        ("Right", "#16a34a", []),
        ("Acted when it should have asked", "#dc2626", ["missed_ask"]),
        ("Asked when it didn't need to", "#f59e0b", ["unnecessary_ask"]),
        ("Made a duplicate agent", "#7c3aed", ["duplicate"]),
        ("Other errors", "#6b7280", ["wrong_person", "wrong_agent", "bad_question", "extra_agents", "unnecessary_agent", "failed"]),
    ]
    width, height, left, bar_h = 720, 260, 170, 44
    span = width - left - 30
    body = [text(left, 26, f"What happened to each message: {world} world, {roster} agents", 16, weight="600")]
    for row, (version, label) in enumerate((("v0", "Original"), (winner, "Records and lookup"))):
        s = data[version][roster]
        n, errors = s["n"], s["errors"]
        counts = [n - sum(errors.values())] + [sum(errors.get(e, 0) for e in keys) for _, _, keys in parts[1:]]
        y0 = 50 + row * (bar_h + 22)
        body.append(text(left - 10, y0 + bar_h / 2 + 5, label, 13, "end", weight="600"))
        x = left
        for (name, colour, _), count in zip(parts, counts):
            w = span * count / n
            if w > 0:
                body.append(f'<rect x="{x:.1f}" y="{y0}" width="{w:.1f}" height="{bar_h}" fill="{colour}"/>')
                if w > 34:
                    body.append(text(x + w / 2, y0 + bar_h / 2 + 5, f"{100 * count / n:.0f}%", 12, "middle", "white", "600"))
            x += w
    for i, (name, colour, _) in enumerate(parts):
        lx, ly = left + (i % 2) * 270, 190 + (i // 2) * 20
        body.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" fill="{colour}"/>')
        body.append(text(lx + 18, ly, name, 12, colour="#374151"))
    return svg(width, height, body, "Outcome of each message, original against records and lookup")


def main(winner: str = "v2") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dev = collect("dev")
    (OUT / "tokens.svg").write_text(tokens_chart(dev, winner))
    (OUT / "outcomes.svg").write_text(outcomes_chart(dev, winner, "dev"))
    held = collect("heldout")
    (OUT / "outcomes-heldout.svg").write_text(outcomes_chart(held, winner, "held-out"))
    print(f"wrote {OUT}/tokens.svg, outcomes.svg, outcomes-heldout.svg")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "v2")
