"""Text fitting.

Pure: takes a measuring function, returns point sizes and wrapped lines. No
ReportLab import, so the shrink logic is testable without a canvas.

Badges are the one place in this stack where getting layout wrong costs money —
a misaligned or overflowing run is a wasted sheet of Avery stock, and you find
out at the printer, not in CI.
"""

from __future__ import annotations

from collections.abc import Callable

#: ``(text, font_size) -> width in points``.
Measure = Callable[[str, float], float]


def fit_single_line(
    text: str,
    *,
    measure: Measure,
    max_width: float,
    pt_max: float,
    pt_min: float,
    step: float = 0.5,
) -> float:
    """Largest size in ``[pt_min, pt_max]`` at which ``text`` fits on one line.

    Returns ``pt_min`` if nothing fits — the caller then decides whether to wrap
    or to truncate. Shrinking below the floor would produce a badge nobody can
    read across a table, which is worse than a slightly clipped one.
    """
    if not text:
        return pt_max
    size = pt_max
    while size > pt_min:
        if measure(text, size) <= max_width:
            return size
        size -= step
    return pt_min


def wrap(text: str, *, measure: Measure, max_width: float, size: float) -> list[str]:
    """Greedy word wrap at a fixed size.

    A single word longer than the line is left on its own line rather than being
    broken: hyphenating somebody's surname on their badge is worse than letting
    it run close to the edge.
    """
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if measure(candidate, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_block(
    text: str,
    *,
    measure: Measure,
    max_width: float,
    max_height: float,
    pt_max: float,
    pt_min: float,
    leading_ratio: float = 1.18,
    step: float = 0.5,
) -> tuple[float, list[str]]:
    """Largest size at which ``text`` wraps into the available box.

    Returns ``(size, lines)``. At ``pt_min`` the block is truncated to the number
    of lines that fit rather than overflowing into the card below it.
    """
    if not text:
        return pt_max, []

    size = pt_max
    while size >= pt_min:
        lines = wrap(text, measure=measure, max_width=max_width, size=size)
        if len(lines) * size * leading_ratio <= max_height:
            return size, lines
        if size == pt_min:
            break
        size = max(pt_min, size - step)

    lines = wrap(text, measure=measure, max_width=max_width, size=pt_min)
    max_lines = max(1, int(max_height // (pt_min * leading_ratio)))
    return pt_min, lines[:max_lines]
