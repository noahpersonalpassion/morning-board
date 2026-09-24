"""Ranking the country by corroboration instead of by one editor's order.

The claim this panel now makes is narrow and worth stating precisely: that
counting how many independent newsrooms carried a story is a measurement,
whereas the order inside any one newsroom's feed is a judgement. These tests
check the measurement behaves, and — more importantly — that it refuses to
pretend when it cannot be taken.
"""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from board.panels.base import State  # noqa: E402
from board.panels.country import (  # noqa: E402
    CountryPanel, cluster_headlines, set_aside,
)
from notice.novelty import Headline, HeadlineCorpus  # noqa: E402

NOW = datetime.now(timezone.utc)


@contextmanager
def _fake_feed(items):
    """Stand in for the RSS fetch so the fallback path is testable offline."""
    import board.panels.country as mod

    real = mod.read
    mod.read = lambda url, timeout=25: [
        SimpleNamespace(title=t, summary=s, link="https://example.test/1",
                        published=NOW, item_id="1", categories=[])
        for t, s in items
    ]
    try:
        yield
    finally:
        mod.read = real


def h(title, outlet, hours_ago=2):
    return Headline(title=title, outlet=outlet,
                    published=NOW - timedelta(hours=hours_ago))


def corpus_of(headlines, outlets):
    c = HeadlineCorpus(window_days=7)
    c.headlines = headlines
    c.outlets_ok = outlets
    return c


class TestClustering(unittest.TestCase):
    def test_same_story_across_outlets_merges(self):
        got = cluster_headlines([
            h("Reserve Bank lifts official cash rate to 4.5 percent", "RNZ"),
            h("Official cash rate raised to 4.5 percent by Reserve Bank", "Stuff"),
        ])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].outlets, ["RNZ", "Stuff"])

    def test_different_stories_stay_apart(self):
        got = cluster_headlines([
            h("Reserve Bank lifts official cash rate to 4.5 percent", "RNZ"),
            h("Wellington ferry terminal closed after storm damage", "Stuff"),
        ])
        self.assertEqual(len(got), 2)

    def test_shortest_headline_wins(self):
        """Length in a headline is mostly angle, so the shortest is plainest."""
        got = cluster_headlines([
            h("Shock as Reserve Bank stuns markets with brutal cash rate hike "
              "that will devastate homeowners", "Outlet A"),
            h("Reserve Bank raises cash rate", "Outlet B"),
        ])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].plainest.title, "Reserve Bank raises cash rate")

    def test_a_cluster_does_not_swallow_the_feed(self):
        """Identity is what members agree on, so vocabulary cannot accumulate.

        With a union rule a cluster grows its term set with every join and
        eventually matches anything; intersecting keeps it pinned to the
        story it started as.
        """
        got = cluster_headlines([
            h("Auckland council votes on transport budget changes", "A"),
            h("Auckland council transport budget vote delayed again", "B"),
            h("Christchurch hospital waiting lists grow further", "C"),
            h("Dunedin students protest housing costs downtown", "D"),
        ])
        self.assertGreaterEqual(len(got), 3)

    def test_very_short_headlines_are_ignored(self):
        self.assertEqual(cluster_headlines([h("Breaking news", "RNZ")]), [])

    def test_a_cluster_keeps_growing_past_two(self):
        """Four newsrooms, four wordings, one event.

        The cluster rule now matches against the seed headline's terms,
        which never change. The intersect-on-join version it replaced also
        passes this case — the seed rule was adopted for being stable and
        explainable ("everything here shares three significant words with
        the first headline seen"), not because intersection was breaking
        this. Low corroboration counts on the live board came from there
        being four readable newsrooms in the country, not from the maths.
        """
        got = cluster_headlines([
            h("Fast-track application to expand West Coast mine rejected", "A"),
            h("West Coast mine expansion rejected under fast-track law", "B"),
            h("Panel rejects fast-track bid to expand West Coast mine", "C"),
            h("Fast-track panel turns down West Coast mine expansion", "D"),
        ])
        self.assertEqual(len(got), 1, [c.outlets for c in got])
        self.assertEqual(got[0].outlets, ["A", "B", "C", "D"])


class TestSetAside(unittest.TestCase):
    def test_sport_is_set_aside(self):
        self.assertEqual(
            set_aside("Kiwi sailor gears up for America's Cup showdown"),
            "sport")

    def test_civic_news_is_kept(self):
        self.assertEqual(
            set_aside("Fast-track application to expand West Coast mine rejected"),
            "")

    def test_the_count_is_printed_not_hidden(self):
        """A silent filter is indistinguishable from a quiet news day."""
        panel = CountryPanel(corpus=corpus_of([
            h("Council votes to raise rates by four percent", "A"),
            h("Rates rise of four percent approved by council", "B"),
            h("All Blacks name squad for northern tour", "A"),
            h("Black Caps collapse in second test match", "B"),
        ], ["A", "B"]))
        r = panel.render()
        self.assertEqual(r.meta["set_aside"], 2)
        self.assertIn("setting aside 2", r.note)
        titles = " ".join(s["title"] for s in r.meta["stories"])
        self.assertNotIn("All Blacks", titles)


class TestPanel(unittest.TestCase):
    def test_ranks_by_number_of_outlets(self):
        panel = CountryPanel(corpus=corpus_of([
            h("Cabinet approves new hospital funding package", "A"),
            h("New hospital funding package approved by Cabinet", "B"),
            h("Cabinet signs off hospital funding package", "C"),
            h("Ferry sailings cancelled across Cook Strait today", "A"),
        ], ["A", "B", "C"]))

        r = panel.render()
        self.assertIs(r.state, State.LIVE)
        stories = r.meta["stories"]
        self.assertEqual(stories[0]["outlets"], 3)
        self.assertIn("hospital", stories[0]["title"].lower())
        self.assertEqual(r.meta["method"], "corroboration")

    def test_stale_headlines_are_not_the_country_today(self):
        panel = CountryPanel(corpus=corpus_of([
            h("Cabinet approves new hospital funding package", "A", hours_ago=200),
            h("New hospital funding package approved by Cabinet", "B", hours_ago=200),
        ], ["A", "B"]))
        self.assertIs(panel.render().state, State.QUIET)

    def test_one_outlet_refuses_to_count(self):
        """A corroboration count over one feed is not a weak measurement.

        It is no measurement at all, so the panel must drop to the single-
        feed path rather than report every story as "1 outlet" and let the
        ordering look like it means something.
        """
        panel = CountryPanel(corpus=corpus_of(
            [h("Cabinet approves new hospital funding package", "A")], ["A"]))
        with _fake_feed([("Ferry sailings cancelled", "")]):
            r = panel.render()
        self.assertEqual(r.meta["method"], "recency")

    def test_fallback_declares_itself(self):
        """The reader must never be shown one running order as the country's."""
        panel = CountryPanel(corpus=None)
        with _fake_feed([("Ferry sailings cancelled today", "Cook Strait")]):
            r = panel.render()
        self.assertEqual(r.flag, "one source")
        self.assertIn("running order", r.effect)
        self.assertIn("one newsroom", r.note)


if __name__ == "__main__":
    unittest.main()
