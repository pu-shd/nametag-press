"""The badge renderer. One engine, ReportLab.

The browser gets a PDF preview of exactly this output rather than a CSS
approximation of it, so what staff see before printing is what prints.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as pdfcanvas

from .fit import fit_block, fit_single_line
from .layout import PAGE_HEIGHT, PAGE_WIDTH, Layout, page_count

logger = logging.getLogger("nametag_press.render")

NAME_FONT = "Times-Bold"
BODY_FONT = "Helvetica"
ROLE_FONT = "Helvetica-Bold"

PAD = 12.0
NEUTRAL = HexColor("#6c757d")


@dataclass(frozen=True)
class Badge:
    """Everything printed on one card."""

    first_name: str | None = None
    last_name: str | None = None
    affiliation: str | None = None
    role_label: str | None = None
    role_color: str | None = None

    @property
    def display_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p).strip()


def _measure(font: str):
    def _m(text: str, size: float) -> float:
        return pdfmetrics.stringWidth(text, font, size)

    return _m


def _color(value: str | None):
    if not value:
        return NEUTRAL
    try:
        return HexColor(value)
    except Exception:  # noqa: BLE001 - a bad colour must not stop a print run
        logger.warning("unusable role colour %r; falling back to neutral", value)
        return NEUTRAL


def draw_card(
    c: pdfcanvas.Canvas,
    badge: Badge,
    *,
    layout: Layout,
    x: float,
    y: float,
    header_text: str | None = None,
    logo: ImageReader | None = None,
    show_outline: bool = False,
) -> None:
    """Draw one badge with its bottom-left corner at ``(x, y)``."""
    if show_outline:
        c.setStrokeColor(HexColor("#cccccc"))
        c.setLineWidth(0.4)
        c.rect(x, y, layout.card_w, layout.card_h)

    inner_w = layout.card_w - 2 * PAD
    top = y + layout.card_h - PAD

    # Header: logo left, event name right of it.
    header_h = 0.0
    if logo is not None or header_text:
        header_h = min(0.5 * INCH_SAFE, layout.card_h * 0.18)
        if logo is not None:
            try:
                c.drawImage(
                    logo, x + PAD, top - header_h, width=header_h * 1.9,
                    height=header_h, preserveAspectRatio=True, anchor="sw", mask="auto",
                )
            except Exception:  # noqa: BLE001
                # A corrupt logo must degrade visibly in the log, not silently
                # draw nothing — the predecessor swallowed this with a bare except.
                logger.warning("logo could not be drawn on a badge", exc_info=True)
        if header_text:
            c.setFont(BODY_FONT, 8)
            c.setFillColor(HexColor("#555555"))
            c.drawRightString(x + layout.card_w - PAD, top - header_h * 0.62, header_text)

    # Role strip at the bottom.
    role_h = 0.0
    if badge.role_label:
        role_h = 14.0
        c.setFont(ROLE_FONT, 9)
        c.setFillColor(_color(badge.role_color))
        c.drawString(x + PAD, y + PAD, badge.role_label.upper())

    body_top = top - header_h - 4
    body_bottom = y + PAD + role_h + 4
    body_h = max(body_top - body_bottom, 10.0)

    name = badge.display_name
    aff = (badge.affiliation or "").strip()

    aff_size = 0.0
    aff_lines: list[str] = []
    if aff:
        aff_size, aff_lines = fit_block(
            aff,
            measure=_measure(BODY_FONT),
            max_width=inner_w,
            max_height=body_h * 0.42,
            pt_max=layout.affiliation_pt_max,
            pt_min=layout.affiliation_pt_min,
        )

    aff_block = len(aff_lines) * aff_size * 1.18
    name_size = fit_single_line(
        name,
        measure=_measure(NAME_FONT),
        max_width=inner_w,
        pt_max=layout.name_pt_max,
        pt_min=layout.name_pt_min,
    )

    centre = body_bottom + (body_h + aff_block) / 2
    c.setFont(NAME_FONT, name_size)
    c.setFillColor(HexColor("#1a1a1a"))
    c.drawCentredString(x + layout.card_w / 2, centre, name)

    cursor = centre - aff_size * 1.35
    c.setFont(BODY_FONT, aff_size or 1)
    c.setFillColor(HexColor("#444444"))
    for line in aff_lines:
        c.drawCentredString(x + layout.card_w / 2, cursor, line)
        cursor -= aff_size * 1.18


INCH_SAFE = 72.0


def render_badges(
    badges: list[Badge],
    *,
    layout: Layout,
    header_text: str | None = None,
    logo_bytes: bytes | None = None,
    show_outline: bool = False,
) -> bytes:
    """Render badges to a PDF."""
    logo = None
    if logo_bytes:
        try:
            logo = ImageReader(io.BytesIO(logo_bytes))
        except Exception:  # noqa: BLE001
            logger.warning("uploaded logo could not be read; printing without it",
                           exc_info=True)

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    c.setTitle("Name badges")

    for i, badge in enumerate(badges):
        if i and i % layout.per_page == 0:
            c.showPage()
        x, y = layout.origin(i)
        draw_card(c, badge, layout=layout, x=x, y=y, header_text=header_text,
                  logo=logo, show_outline=show_outline)

    if not badges:
        c.setFont(BODY_FONT, 12)
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2, "No badges selected.")

    c.save()
    return buf.getvalue()


def render_blank(layout: Layout, *, sheets: int = 1) -> bytes:
    """Outlined but empty sheets, for calibrating a printer.

    Print one on plain paper and hold it against real stock before committing a
    box of Avery to a run. A passing test suite and a misaligned sheet are
    entirely compatible.
    """
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    c.setTitle(f"Calibration — {layout.sku}")

    for sheet in range(max(1, sheets)):
        if sheet:
            c.showPage()
        for slot in range(layout.per_page):
            x, y = layout.origin(slot)
            c.setStrokeColor(HexColor("#999999"))
            c.setLineWidth(0.5)
            c.rect(x, y, layout.card_w, layout.card_h)
            c.setFont(BODY_FONT, 7)
            c.setFillColor(HexColor("#999999"))
            c.drawString(x + 4, y + 4, f"{layout.sku} · slot {slot + 1}")

    c.save()
    return buf.getvalue()


__all__ = ["Badge", "draw_card", "page_count", "render_badges", "render_blank"]
