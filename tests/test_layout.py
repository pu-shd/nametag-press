"""Sheet geometry and text fitting.

Badges are the one place in this stack where a bug costs money: a misaligned run
wastes a box of Avery stock, and you find out at the printer. These are pure
tests of the numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nametag_press.fit import fit_block, fit_single_line, wrap
from nametag_press.layout import (
    INCH,
    LAYOUTS,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    get,
    page_count,
    to_json_dict,
)

LAYOUTS_JSON = Path(__file__).resolve().parents[1] / "src/nametag_press/static/layouts.json"


class TestGeometryFitsThePage:
    @pytest.mark.parametrize("sku", sorted(LAYOUTS))
    def test_fits_within_letter_width(self, sku):
        """The assertion that catches an arithmetic slip before a box of stock does."""
        layout = LAYOUTS[sku]
        assert layout.used_width <= PAGE_WIDTH + 0.01, (
            f"{sku} is {layout.used_width / INCH:.3f}in wide, wider than the page"
        )

    @pytest.mark.parametrize("sku", sorted(LAYOUTS))
    def test_fits_within_letter_height(self, sku):
        layout = LAYOUTS[sku]
        assert layout.used_height <= PAGE_HEIGHT + 0.01

    @pytest.mark.parametrize("sku", sorted(LAYOUTS))
    def test_no_card_escapes_the_page(self, sku):
        layout = LAYOUTS[sku]
        for slot in range(layout.per_page):
            x, y = layout.origin(slot)
            assert x >= -0.01 and y >= -0.01
            assert x + layout.card_w <= PAGE_WIDTH + 0.01
            assert y + layout.card_h <= PAGE_HEIGHT + 0.01

    @pytest.mark.parametrize("sku", sorted(LAYOUTS))
    def test_slots_do_not_overlap(self, sku):
        layout = LAYOUTS[sku]
        boxes = [layout.origin(i) for i in range(layout.per_page)]
        assert len(set(boxes)) == layout.per_page


class TestKnownStocks:
    def test_74541_and_5392_are_the_same_stock(self):
        """Two part numbers, one physical sheet. Both exist so an operator can pick
        whichever number is printed on the box in front of them."""
        a, b = LAYOUTS["74541"], LAYOUTS["5392"]
        for field in ("card_w", "card_h", "cols", "rows", "margin_x", "margin_y",
                      "gap_x", "gap_y"):
            assert getattr(a, field) == getattr(b, field)

    def test_six_up_dimensions(self):
        layout = LAYOUTS["5392"]
        assert (layout.card_w, layout.card_h) == (4.0 * INCH, 3.0 * INCH)
        assert (layout.cols, layout.rows, layout.per_page) == (2, 3, 6)
        assert (layout.margin_x, layout.margin_y) == (0.25 * INCH, 1.0 * INCH)
        assert (layout.gap_x, layout.gap_y) == (0.0, 0.0)

    def test_eight_up_dimensions(self):
        layout = LAYOUTS["5395"]
        assert (layout.card_w, layout.card_h) == (3.375 * INCH, 2.33 * INCH)
        assert (layout.cols, layout.rows, layout.per_page) == (2, 4, 8)
        assert (layout.margin_x, layout.margin_y) == (0.75 * INCH, 0.5 * INCH)
        assert (layout.gap_x, layout.gap_y) == (0.25 * INCH, 0.1 * INCH)

    def test_first_slot_is_the_top_left(self):
        """ReportLab's origin is bottom-left; badges read top-to-bottom."""
        layout = LAYOUTS["5392"]
        x, y = layout.origin(0)
        assert x == pytest.approx(layout.margin_x)
        assert y + layout.card_h == pytest.approx(PAGE_HEIGHT - layout.margin_y)

    def test_unknown_sku_falls_back_rather_than_raising(self):
        """A badge run happens the evening before an event. Print something."""
        assert get("nonsense").sku == "5392"
        assert get(None).sku == "5392"


class TestPageCount:
    @pytest.mark.parametrize(
        ("n", "expected"), [(0, 0), (1, 1), (6, 1), (7, 2), (12, 2), (13, 3)]
    )
    def test_six_up(self, n, expected):
        assert page_count(n, LAYOUTS["5392"]) == expected

    def test_eight_up(self):
        assert page_count(9, LAYOUTS["5395"]) == 2


class TestLayoutsJsonIsGenerated:
    def test_shipped_file_matches_the_module(self):
        """The browser draws the selection grid from this file; the renderer uses
        the module. If they drift, the preview lies about what will print."""
        shipped = json.loads(LAYOUTS_JSON.read_text())
        assert shipped == json.loads(json.dumps(to_json_dict())), (
            "layouts.json is stale. Regenerate it:\n"
            "  python -c \"import json,sys; sys.path.insert(0,'src'); "
            "from nametag_press.layout import to_json_dict; "
            "print(json.dumps(to_json_dict(), indent=2, sort_keys=True))\" "
            "> src/nametag_press/static/layouts.json"
        )


def measure(text: str, size: float) -> float:
    """A predictable stand-in: every glyph is 0.5em wide."""
    return len(text) * size * 0.5


class TestFitSingleLine:
    def test_short_text_keeps_the_maximum(self):
        assert fit_single_line("Ada", measure=measure, max_width=500,
                               pt_max=22, pt_min=12) == 22

    def test_long_text_shrinks_to_fit(self):
        """20 glyphs at 0.5em need 10pt of width each: 22pt overflows 200, 20pt fits."""
        text = "A" * 20
        size = fit_single_line(text, measure=measure, max_width=200,
                               pt_max=22, pt_min=12)
        assert 12 < size < 22
        assert measure(text, size) <= 200

    def test_never_below_the_floor(self):
        """A badge nobody can read across a table is worse than a clipped one."""
        assert fit_single_line("A" * 500, measure=measure, max_width=50,
                               pt_max=22, pt_min=12) == 12

    def test_monotonic_in_length(self):
        sizes = [
            fit_single_line("A" * n, measure=measure, max_width=200, pt_max=22, pt_min=8)
            for n in (5, 20, 60, 200)
        ]
        assert sizes == sorted(sizes, reverse=True)

    def test_empty_text(self):
        assert fit_single_line("", measure=measure, max_width=10,
                               pt_max=22, pt_min=12) == 22


class TestWrap:
    def test_wraps_on_words(self):
        lines = wrap("one two three four", measure=measure, max_width=40, size=10)
        assert len(lines) > 1
        assert " ".join(lines) == "one two three four"

    def test_a_single_long_word_is_not_broken(self):
        """Hyphenating somebody's surname on their badge is worse than a tight fit."""
        lines = wrap("Llanfairpwllgwyngyll", measure=measure, max_width=10, size=10)
        assert lines == ["Llanfairpwllgwyngyll"]

    def test_empty(self):
        assert wrap("   ", measure=measure, max_width=100, size=10) == []


class TestFitBlock:
    def test_fits_at_full_size_when_short(self):
        size, lines = fit_block("Example University", measure=measure, max_width=400,
                                max_height=100, pt_max=12, pt_min=8)
        assert size == 12
        assert lines == ["Example University"]

    def test_shrinks_then_truncates(self):
        size, lines = fit_block(" ".join(["word"] * 200), measure=measure,
                                max_width=80, max_height=30, pt_max=12, pt_min=8)
        assert size == 8
        assert len(lines) * 8 * 1.18 <= 30 + 0.01

    def test_empty_block(self):
        size, lines = fit_block("", measure=measure, max_width=100, max_height=100,
                                pt_max=12, pt_min=8)
        assert lines == []
