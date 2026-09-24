"""Compartments, scales and icons.

The rule under test throughout: **size is a claim.** A grid of equal boxes
asserts its contents matter equally, and that stops being true the moment
one is a deadline you can permanently miss and another is a row with
nothing to report. So shape follows state, never the layout's convenience.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from board.glyphs import ICONS, icon  # noqa: E402
from board.panels.base import PanelResult, Scale, State  # noqa: E402
from board.render import _bar, _metric, _strip, render_page  # noqa: E402


class TestShape(unittest.TestCase):
    def test_urgent_gets_a_card(self):
        r = PanelResult(state=State.URGENT, reading="1")
        self.assertEqual(r.shape, "card")

    def test_live_gets_a_tile(self):
        r = PanelResult(state=State.LIVE, reading="320")
        self.assertEqual(r.shape, "metric")

    def test_nothing_to_report_gets_a_strip(self):
        """A quiet row is true and cheap, and should cost almost no page."""
        for state in (State.QUIET, State.OFF, State.UNREAD, State.PAUSED):
            with self.subTest(state=state):
                self.assertEqual(
                    PanelResult(state=state, reading="Nothing").shape, "strip")


class TestScale(unittest.TestCase):
    def test_midpoint(self):
        self.assertAlmostEqual(Scale(value=5, low=0, high=10).pct, 50.0)

    def test_value_above_the_band_clamps(self):
        """A band drawn wrong should look wrong, not spill off the tile."""
        self.assertEqual(Scale(value=99, low=0, high=10).pct, 100.0)

    def test_value_below_the_band_clamps(self):
        self.assertEqual(Scale(value=-5, low=0, high=10).pct, 0.0)

    def test_zero_width_band_does_not_divide_by_zero(self):
        self.assertEqual(Scale(value=7, low=7, high=7).pct, 0.0)

    def test_no_scale_draws_no_bar(self):
        """An empty track reads as zero, which is a measurement not taken."""
        self.assertEqual(_bar(None), "")

    def test_a_scale_draws_its_width(self):
        html = _bar(Scale(value=8, low=0, high=10, tone="alert"))
        self.assertIn("width:80.0%", html)
        self.assertIn("fill alert", html)


class TestIcons(unittest.TestCase):
    def test_every_icon_is_a_closed_svg(self):
        for name, svg in ICONS.items():
            with self.subTest(icon=name):
                self.assertTrue(svg.startswith("<svg"))
                self.assertTrue(svg.endswith("</svg>"))

    def test_icons_inherit_colour(self):
        """One glyph set, tinted by its tile — no palette to keep in sync."""
        self.assertIn('stroke="currentColor"', ICONS["fuel"])

    def test_unknown_icon_falls_back_rather_than_vanishing(self):
        """A typo in a panel must not cost a tile its left column."""
        self.assertEqual(icon("nonsense"), ICONS["blank"])
        self.assertEqual(icon(""), ICONS["blank"])

    def test_nothing_loads_from_the_network(self):
        for name, svg in ICONS.items():
            with self.subTest(icon=name):
                self.assertNotIn("http", svg)


class TestTwoIconModules(unittest.TestCase):
    """Both icon modules must exist and keep their own jobs.

    `board/glyphs.py` holds the inline SVG marks inside the tiles;
    `board/icons.py` draws the PNG home-screen icon at build time. They were
    briefly the same filename, and the collision replaced the icon generator
    without a word — the build only failed later, in pwa.py, importing a
    name that had quietly ceased to exist. A module is a namespace, and
    writing over one destroys whatever was there.
    """

    def test_the_png_icon_writer_survives(self):
        from board.icons import SIZES, write_icons
        self.assertIn(180, SIZES)
        self.assertTrue(callable(write_icons))

    def test_the_tile_glyphs_are_separate(self):
        from board import glyphs, icons
        self.assertIsNot(glyphs, icons)
        self.assertFalse(hasattr(icons, "ICONS"))
        self.assertFalse(hasattr(glyphs, "write_icons"))

    def test_pwa_can_still_import_what_it_needs(self):
        """The import that actually broke the build."""
        from board.pwa import write_pwa
        self.assertTrue(callable(write_pwa))


class TestTileMarkup(unittest.TestCase):
    def test_a_tile_carries_its_label_for_whats_new(self):
        html = _metric("Fuel", PanelResult(state=State.LIVE, reading="320",
                                           icon="fuel"))
        self.assertIn('data-label="Fuel"', html)

    def test_a_strip_falls_back_to_the_note_when_there_is_no_effect(self):
        html = _strip("Bins", PanelResult(state=State.OFF,
                                          reading="Not connected",
                                          note="Needs your council zone."))
        self.assertIn("Needs your council zone.", html)


class TestMethodDisclosure(unittest.TestCase):
    """"Auditable" only means something if the rules are on the page."""

    def method(self, rows):
        from board.render import _method
        return _method(rows)

    def test_a_row_that_reported_nothing_is_still_listed(self):
        """The rows a reader is most entitled to be suspicious of.

        A panel that checked and found nothing and a panel that never ran
        look identical from outside. The log is what separates them.
        """
        html = self.method([
            ("Near you", PanelResult(state=State.QUIET, reading="Nothing",
                                     why="Read 41 notices. None named a place "
                                         "you gave this board.")),
        ])
        self.assertIn("Near you", html)
        self.assertIn("Read 41 notices", html)

    def test_rule_and_source_both_appear(self):
        html = self.method([
            ("Fuel", PanelResult(state=State.LIVE, reading="320",
                                 why="Past 12 days this row would read "
                                     "'source paused'.",
                                 note="MBIE weekly monitoring.")),
        ])
        self.assertIn("source paused", html)
        self.assertIn("MBIE weekly monitoring", html)

    def test_nothing_to_explain_renders_nothing(self):
        self.assertEqual(
            self.method([("X", PanelResult(state=State.LIVE, reading="1"))]),
            "")

    def test_it_is_folded_away_by_default(self):
        """On the page every morning, in the way on none of them."""
        html = self.method([
            ("Fuel", PanelResult(state=State.LIVE, reading="1", note="MBIE.")),
        ])
        self.assertTrue(html.startswith("<details"))
        self.assertNotIn(" open>", html)


class TestActionLinks(unittest.TestCase):
    """Never a problem without a path out of it."""

    def test_a_tile_renders_its_action(self):
        html = _metric("Fuel", PanelResult(
            state=State.LIVE, reading="320", icon="fuel",
            link_label="Find cheaper nearby", link_url="https://example.test/"))
        self.assertIn('class="act"', html)
        self.assertIn('rel="noopener"', html)
        self.assertIn("Find cheaper nearby", html)

    def test_no_link_renders_no_affordance(self):
        html = _metric("Fuel", PanelResult(state=State.LIVE, reading="320"))
        self.assertNotIn('class="act"', html)

    def test_a_half_specified_link_is_not_rendered(self):
        """A label with no href is a button that does nothing."""
        html = _metric("Fuel", PanelResult(state=State.LIVE, reading="320",
                                           link_label="Go"))
        self.assertNotIn('class="act"', html)

    def test_a_story_links_to_the_version_shown(self):
        from board.render import _country
        html = _country(PanelResult(state=State.LIVE, reading="1", meta={
            "stories": [{"title": "Mine expansion rejected", "where": "",
                         "outlets": 2, "outlet_names": ["RNZ", "Stuff"],
                         "url": "https://example.test/a"}]}))
        self.assertIn('href="https://example.test/a"', html)

    def test_a_story_without_a_url_is_still_shown(self):
        from board.render import _country
        html = _country(PanelResult(state=State.LIVE, reading="1", meta={
            "stories": [{"title": "Mine expansion rejected", "where": "",
                         "outlets": 2, "outlet_names": ["RNZ"]}]}))
        self.assertIn("Mine expansion rejected", html)
        self.assertNotIn("<a href", html)


class TestPageAssembly(unittest.TestCase):
    def page(self, rows):
        country = PanelResult(state=State.LIVE, reading="0",
                              meta={"stories": [], "cap": 5, "source": "T"})
        return render_page(site_name="Board", place="Here", rows=rows,
                           country=country)

    def test_each_kind_lands_in_its_own_compartment(self):
        html = self.page([
            ("Deadlines", PanelResult(state=State.URGENT, reading="1",
                                      icon="clock", effect="Closes soon.")),
            ("Fuel", PanelResult(state=State.LIVE, reading="320", icon="fuel",
                                 effect="$160 a tank.",
                                 scale=Scale(value=320, low=300, high=330))),
            ("Near you", PanelResult(state=State.QUIET, reading="Nothing",
                                     icon="pin", effect="No change.")),
        ])
        self.assertEqual(html.count('class="card"'), 1)
        self.assertEqual(html.count('class="tile"'), 1)
        self.assertEqual(html.count('class="strip"'), 1)

    def test_a_chart_gets_its_own_full_width_tile(self):
        """Seven bars in a half-width tile is a smear, not a chart."""
        html = self.page([
            ("Weather", PanelResult(state=State.LIVE, reading="12", icon="weather",
                                    extra_html='<div class="week">x</div>')),
        ])
        self.assertIn('class="tile wide"', html)

    def test_the_page_never_breaks_its_own_css(self):
        html = self.page([("Fuel", PanelResult(state=State.LIVE, reading="1"))])
        self.assertEqual(html.count("<style>"), 1)
        self.assertEqual(html.count("</style>"), 1)
        self.assertNotIn("<!--", html.split("<body>")[1])


if __name__ == "__main__":
    unittest.main()
