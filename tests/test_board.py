"""The board's own rules: panel safety, the off-row collapse, what's-new."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from board.panels.base import PanelResult, State, safe_render  # noqa: E402
from board.panels.daylight import _clock, _delta_phrase  # noqa: E402
from board.render import _first_clause, _off_summary, render_page  # noqa: E402
from board.whatsnew import state_blob  # noqa: E402


class Exploding:
    panel_id, label = "boom", "Boom"

    def render(self):
        raise RuntimeError("the wire fell over")


class TestPanelSafety(unittest.TestCase):
    def test_a_panel_cannot_take_the_board_down(self):
        r = safe_render(Exploding())
        self.assertEqual(r.state, State.UNREAD)

    def test_a_failure_names_itself_rather_than_vanishing(self):
        """An absent row and a row with nothing to report look identical to
        a reader, and only one of them is true."""
        r = safe_render(Exploding())
        self.assertIn("Boom", r.note)
        self.assertIn("RuntimeError", r.note)
        self.assertIn("stale", r.note)


class TestOffCollapse(unittest.TestCase):
    def rows(self, n):
        return [
            (f"Row {i}", PanelResult(state=State.OFF, reading="Not connected",
                                     note="Needs a thing. More words here."))
            for i in range(n)
        ]

    def test_no_off_rows_renders_nothing(self):
        self.assertEqual(_off_summary([]), "")

    def test_off_rows_collapse_to_one_row(self):
        html = _off_summary(self.rows(3))
        self.assertEqual(html.count("<li "), 1)
        self.assertIn('data-state="off"', html)
        self.assertIn(">3<", html)

    def test_collapsed_row_still_names_every_one(self):
        """Collapsing is a layout fix, not a way to hide an unbuilt row."""
        html = _off_summary(self.rows(3))
        for i in range(3):
            self.assertIn(f"Row {i}", html)

    def test_first_clause_reads_as_a_sentence_fragment(self):
        self.assertEqual(
            _first_clause("Needs a Gazette API key. Request one from x."),
            "needs a Gazette API key",
        )


class TestWhatsNew(unittest.TestCase):
    def blob(self, rows):
        raw = state_blob(rows)
        return json.loads(raw.split(">", 1)[1].rsplit("<", 1)[0])

    def test_off_rows_are_not_tracked(self):
        """An unbuilt row cannot 'change', and marking it would be noise."""
        rows = [
            ("Live", PanelResult(state=State.LIVE, reading="1")),
            ("Off", PanelResult(state=State.OFF, reading="Not connected")),
        ]
        self.assertEqual(list(self.blob(rows)), ["Live"])

    def test_same_reading_same_note_is_not_a_change(self):
        a = [("Fuel", PanelResult(state=State.LIVE, reading="320",
                                  unit="c/L", note="Week ending 18 Sep."))]
        b = [("Fuel", PanelResult(state=State.LIVE, reading="320",
                                  unit="c/L", note="Week ending 18 Sep."))]
        self.assertEqual(self.blob(a), self.blob(b))

    def test_a_moved_number_is_a_change(self):
        a = [("Fuel", PanelResult(state=State.LIVE, reading="320", unit="c/L"))]
        b = [("Fuel", PanelResult(state=State.LIVE, reading="324", unit="c/L"))]
        self.assertNotEqual(self.blob(a), self.blob(b))


class TestDaylight(unittest.TestCase):
    def test_clock_reads_as_speech(self):
        from datetime import datetime
        self.assertEqual(_clock(datetime(2026, 9, 24, 19, 42)), "7:42pm")
        self.assertEqual(_clock(datetime(2026, 9, 24, 6, 5)), "6:05am")
        self.assertEqual(_clock(datetime(2026, 9, 24, 0, 30)), "12:30am")

    def test_delta_is_plain_english(self):
        self.assertEqual(_delta_phrase(2), "2 minutes later than yesterday.")
        self.assertEqual(_delta_phrase(1), "1 minute later than yesterday.")
        self.assertEqual(_delta_phrase(-3), "3 minutes earlier than yesterday.")
        self.assertEqual(_delta_phrase(0), "The same as yesterday.")


if __name__ == "__main__":
    unittest.main()


class TestPageStructure(unittest.TestCase):
    """Regression: the what's-new CSS marker sits inside the page's own
    <style> block, so its replacement must be bare CSS. Wrapping it in a
    second <style> nested one inside the other, and the inner closing tag
    ended the outer block early — every rule after it rendered as visible
    text at the top of the live page."""

    def page(self) -> str:
        from board.panels.base import PanelResult, State
        from board.render import render_page
        rows = [("Weather", PanelResult(state=State.LIVE, reading="12°C",
                                        note="Dry all week."))]
        country = PanelResult(state=State.LIVE, reading="0",
                              meta={"stories": [], "cap": 5, "source": "Test"})
        return render_page(site_name="Board", place="Here",
                           rows=rows, country=country)

    def test_style_tags_are_balanced(self):
        html = self.page()
        self.assertEqual(html.count("<style>"), html.count("</style>"))

    def test_no_css_leaks_into_the_body(self):
        html = self.page()
        body = html.split("<body>", 1)[1]
        self.assertNotIn("@media", body)
        self.assertNotIn("grid-template-columns", body)

    def test_every_marker_is_replaced(self):
        import re
        self.assertEqual(re.findall(r"<!--[A-Z]+-->", self.page()), [])


class TestFreshness(unittest.TestCase):
    """The board applying its own rule to itself.

    The service worker serves the cached page first, so after a rebuild the
    reader sees the previous board rendered exactly like a current one — the
    same failure every panel refuses to commit, one level up.
    """

    def page(self):
        from board.panels.base import PanelResult, State
        from board.render import render_page
        rows = [("Weather", PanelResult(state=State.LIVE, reading="12°C"))]
        country = PanelResult(state=State.LIVE, reading="0",
                              meta={"stories": [], "cap": 5, "source": "T"})
        return render_page(site_name="Board", place="Here",
                           rows=rows, country=country)

    def test_page_stamps_its_own_build_time(self):
        import re
        self.assertRegex(self.page(), r"var BUILT = '\d{4}-\d{2}-\d{2}T")

    def test_notice_is_hidden_until_proven_stale(self):
        """It must not flash on a page that is perfectly current."""
        html = self.page()
        self.assertIn('class="stale" id="stale"', html)
        self.assertIn(".stale { \n" if False else ".stale {", html)
        self.assertIn("display: none", html)

    def test_reload_clears_the_cache_first(self):
        """Reloading without dropping the cached shell just serves the same
        stale copy back, and the button looks broken."""
        self.assertIn("caches.delete", self.page())


class TestNextReading(unittest.TestCase):
    """The footer's "next" time must survive daylight saving.

    GitHub's scheduler runs in UTC and does not observe New Zealand summer
    time, so the workflow's fixed 18:00 UTC lands at 6am here in winter and
    7am in summer. The footer used to print the literal string "06:00",
    which meant a board whose whole argument is "never show a stale figure
    as a current one" was quietly wrong about its own next reading for half
    of every year.
    """

    def at(self, iso):
        from board.render import next_reading
        return next_reading(
            datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo("Pacific/Auckland")),
            "Pacific/Auckland")

    def test_standard_time_reads_six(self):
        self.assertEqual(self.at("2026-09-24T17:36"), "6:00am")

    def test_summer_time_reads_seven(self):
        """New Zealand moves to NZDT on 27 September 2026."""
        self.assertEqual(self.at("2026-09-30T17:36"), "7:00am")

    def test_midwinter_reads_six(self):
        self.assertEqual(self.at("2026-07-01T09:00"), "6:00am")

    def test_after_the_fire_it_points_at_tomorrow(self):
        """Read at 7am, the next reading is tomorrow's, not this morning's."""
        self.assertEqual(self.at("2026-07-01T07:30"), "6:00am")


class TestTerminalState(unittest.TestCase):
    """The end of the board must not congratulate and then contradict."""

    def page(self, rows):
        country = PanelResult(state=State.LIVE, reading="0",
                              meta={"stories": [], "cap": 5, "source": "T"})
        return render_page(site_name="Board", place="Here", rows=rows,
                           country=country)

    def foot(self, rows):
        return self.page(rows).split('<footer class="foot">')[1]

    def test_an_open_deadline_is_not_caught_up(self):
        """It read "You're caught up." directly above "1 thing needs you."

        Both were true in their own way; together they were nonsense.
        """
        foot = self.foot([("Deadlines", PanelResult(state=State.URGENT,
                                                    reading="1"))])
        self.assertIn("One thing still needs you.", foot)
        self.assertNotIn("caught up", foot)

    def test_a_clear_board_says_so(self):
        foot = self.foot([("Fuel", PanelResult(state=State.LIVE,
                                               reading="320"))])
        self.assertIn("caught up", foot)
        self.assertIn("Nothing needs you today.", foot)

    def test_an_unread_source_is_caught_up_with_gaps(self):
        """Having seen everything readable is not the same as everything."""
        foot = self.foot([("Fuel", PanelResult(state=State.UNREAD,
                                               reading="Unread"))])
        self.assertIn("with gaps", foot)
        self.assertIn("could not be read", foot)

    def test_plurals(self):
        foot = self.foot([
            ("A", PanelResult(state=State.URGENT, reading="1")),
            ("B", PanelResult(state=State.URGENT, reading="1")),
        ])
        self.assertIn("2 things still need you.", foot)


class TestAlertBar(unittest.TestCase):
    """The bar must be furniture on no morning and unmissable on one."""

    def page(self, alert=None, weather_effect="Rain most days, from Friday",
             rows=None):
        rows = rows if rows is not None else [
            ("Weather", PanelResult(state=State.LIVE, reading="14.2C",
                                    effect=weather_effect,
                                    note="Source: Open-Meteo.")),
        ]
        country = PanelResult(state=State.LIVE, reading="0",
                              meta={"stories": [], "cap": 5, "source": "T"})
        return render_page(site_name="Board", place="Here", rows=rows,
                           country=country, alert=alert)

    def firing(self):
        return PanelResult(state=State.URGENT, reading="M5.9",
                           effect="5 km south of Taumarunui.",
                           note="Met the rule.", flag="geonet",
                           flag_kind="alert")

    def test_quiet_morning_renders_no_bar_at_all(self):
        """Not a hidden bar, not an empty one: no markup.

        An empty alert bar is permanent furniture, and permanent furniture
        in the place alerts appear is how a reader learns to skip that place.
        """
        html = self.page(alert=PanelResult(state=State.QUIET,
                                           reading="Nothing"))
        self.assertNotIn('class="alert"', html)

    def test_no_alert_panel_at_all_is_fine(self):
        self.assertNotIn('class="alert"', self.page(alert=None))

    def test_firing_alert_appears_and_leads_the_page(self):
        html = self.page(alert=self.firing(), rows=[
            ("Deadlines", PanelResult(state=State.URGENT, reading="1",
                                      effect="Closes soon.")),
        ])
        self.assertIn('class="alert"', html)
        self.assertIn("Taumarunui", html)
        lede = html.split('<p class="state">')[1].split("<span")[0]
        self.assertLess(lede.index("M5.9"), lede.index("deadline"))

    def test_lede_does_not_repeat_the_weather_tile(self):
        """The top line answers "must I do anything", not "what is it like".

        Opening the lede with the weather read well when the board was a
        list. Once the weather got a tile of its own four centimetres below,
        the same sentence appeared twice inside one glance — so the weather
        stays in its tile and the lede carries what no tile can.
        """
        html = self.page(weather_effect="Rain most days, from Friday")
        lede = html.split('<p class="state">')[1].split("<span")[0]
        self.assertNotIn("Rain most days", lede)
        self.assertNotIn("Source:", lede)

    def test_lede_always_says_something(self):
        html = self.page(rows=[("Fuel", PanelResult(state=State.LIVE,
                                                    reading="320"))])
        lede = html.split('<p class="state">')[1].split("<span")[0]
        self.assertIn("1 reading taken", lede)
        self.assertNotIn("1 readings", lede)

    def test_unread_alert_is_not_a_bar(self):
        """A failed alert feed must not render as a bar — and must not
        render as nothing either.

        `_alert` deliberately returns empty for any non-URGENT state; the
        other half of the contract lives in build.py, which appends an
        UNREAD alert to the ordinary rows so the reader is told nobody
        looked. This test pins the half that lives here.
        """
        from board.render import _alert
        unread = PanelResult(state=State.UNREAD, reading="Unread",
                             note="Alert could not be read this morning.")
        self.assertEqual(_alert(unread), "")

    def test_page_survives_an_alert_without_breaking_its_own_css(self):
        html = self.page(alert=self.firing())
        self.assertEqual(html.count("<style>"), 1)
        self.assertEqual(html.count("</style>"), 1)
        self.assertNotIn("<!--", html.split("<body>")[1])
