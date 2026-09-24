"""The board's own rules: panel safety, the off-row collapse, what's-new."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from board.panels.base import PanelResult, State, safe_render  # noqa: E402
from board.panels.daylight import _clock, _delta_phrase  # noqa: E402
from board.render import _first_clause, _off_summary  # noqa: E402
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
        self.assertEqual(html.count('<li class="row"'), 1)
        self.assertIn(">3 <", html)

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
