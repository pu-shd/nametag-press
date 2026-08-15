"""Avery sheet geometry — the single source of truth.

In the predecessor this existed **twice**: once in ReportLab and once in a print
CSS grid. They would have diverged on the first tweak, and the CSS version could
not reproduce the renderer's per-line autoshrink, so a long name printed
differently depending on which path you used. That is exactly the failure that
ruins a sheet of Avery stock.

There is now one renderer. ``layouts.json``, which the browser uses to draw the
on-screen selection grid, is **generated** from this module and asserted equal in
CI, so JavaScript can describe the geometry without owning it.

All measurements in points (72 per inch), the unit ReportLab works in.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

INCH = 72.0

#: US Letter. Height is deliberately 10.95in rather than 11in: Avery's own
#: template leaves the last sliver unused, and printers disagree about the
#: bottom margin.
PAGE_WIDTH = 8.5 * INCH
PAGE_HEIGHT = 11.0 * INCH


@dataclass(frozen=True)
class Layout:
    """One Avery stock."""

    sku: str
    label: str
    card_w: float
    card_h: float
    cols: int
    rows: int
    margin_x: float
    margin_y: float
    gap_x: float
    gap_y: float
    name_pt_max: float
    name_pt_min: float
    affiliation_pt_max: float
    affiliation_pt_min: float

    @property
    def per_page(self) -> int:
        return self.cols * self.rows

    @property
    def used_width(self) -> float:
        return self.margin_x * 2 + self.cols * self.card_w + (self.cols - 1) * self.gap_x

    @property
    def used_height(self) -> float:
        return self.margin_y * 2 + self.rows * self.card_h + (self.rows - 1) * self.gap_y

    def origin(self, index: int) -> tuple[float, float]:
        """Bottom-left corner of card ``index`` on its page.

        ReportLab's origin is bottom-left; badges read top-to-bottom, so row 0 is
        the *top* row.
        """
        slot = index % self.per_page
        col = slot % self.cols
        row = slot // self.cols
        x = self.margin_x + col * (self.card_w + self.gap_x)
        y = PAGE_HEIGHT - self.margin_y - (row + 1) * self.card_h - row * self.gap_y
        return x, y

    def as_dict(self) -> dict:
        d = asdict(self)
        d["per_page"] = self.per_page
        return d


#: 74541 and 5392 are the same physical stock under two part numbers. Keeping
#: both means an operator can pick whichever number is printed on the box in
#: front of them.
_SIX_UP = dict(
    card_w=4.0 * INCH,
    card_h=3.0 * INCH,
    cols=2,
    rows=3,
    margin_x=0.25 * INCH,
    margin_y=1.0 * INCH,
    gap_x=0.0,
    gap_y=0.0,
    name_pt_max=22.0,
    name_pt_min=12.0,
    affiliation_pt_max=12.0,
    affiliation_pt_min=8.0,
)

LAYOUTS: dict[str, Layout] = {
    "74541": Layout(sku="74541", label="Avery 74541 — 4 × 3 in, 6 per sheet", **_SIX_UP),
    "5392": Layout(sku="5392", label="Avery 5392 — 4 × 3 in, 6 per sheet", **_SIX_UP),
    "5395": Layout(
        sku="5395",
        label="Avery 5395 — 3⅜ × 2⅓ in, 8 per sheet",
        card_w=3.375 * INCH,
        card_h=2.33 * INCH,
        cols=2,
        rows=4,
        margin_x=0.75 * INCH,
        margin_y=0.5 * INCH,
        gap_x=0.25 * INCH,
        gap_y=0.1 * INCH,
        name_pt_max=16.0,
        name_pt_min=10.0,
        affiliation_pt_max=10.0,
        affiliation_pt_min=8.0,
    ),
}

DEFAULT_SKU = "5392"


def get(sku: str | None) -> Layout:
    """Look up a layout, falling back to the default rather than raising.

    A badge run is time-critical and usually happens the evening before an event.
    An unknown SKU should print something on the commonest stock, not stop.
    """
    return LAYOUTS.get(sku or DEFAULT_SKU, LAYOUTS[DEFAULT_SKU])


def page_count(n_cards: int, layout: Layout) -> int:
    if n_cards <= 0:
        return 0
    return -(-n_cards // layout.per_page)


def to_json_dict() -> dict:
    """What ``layouts.json`` contains. Asserted equal to the shipped file in CI."""
    return {
        "default": DEFAULT_SKU,
        "page": {"width": PAGE_WIDTH, "height": PAGE_HEIGHT},
        "layouts": {sku: layout.as_dict() for sku, layout in LAYOUTS.items()},
    }
