"""Loading several feeds per outlet without inflating the outlet count.

The number this board prints beside a story is *independent newsrooms*. RNZ
publishes a dozen topic feeds; if each read as its own outlet, a single RNZ
story appearing in national, politics and regional would show as "3 outlets"
and the one measurement on the panel would become a fiction.
"""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from notice.feeds import FeedError  # noqa: E402
from notice.novelty import HeadlineCorpus  # noqa: E402

NOW = datetime.now(timezone.utc)


@contextmanager
def feeds(mapping):
    """mapping: {url: [titles] or FeedError}."""
    import notice.novelty as mod

    real = mod.read

    def fake(url, timeout=30):
        got = mapping.get(url)
        if isinstance(got, Exception):
            raise got
        return [SimpleNamespace(title=t, summary="", link="https://x.test/",
                                published=NOW, item_id=t, categories=[])
                for t in (got or [])]

    mod.read = fake
    try:
        yield
    finally:
        mod.read = real


class TestMultiFeedOutlets(unittest.TestCase):
    def test_several_feeds_are_one_outlet(self):
        c = HeadlineCorpus()
        with feeds({"a": ["Council raises rates by four percent"],
                    "b": ["Health budget reallocated across districts"]}):
            c.load_feeds({"RNZ": ["a", "b"]})
        self.assertEqual(c.outlets_ok, ["RNZ"])
        self.assertEqual({h.outlet for h in c.headlines}, {"RNZ"})
        self.assertEqual(len(c.headlines), 2)

    def test_a_story_in_two_of_one_outlets_feeds_is_counted_once(self):
        """Otherwise an outlet corroborates itself."""
        c = HeadlineCorpus()
        with feeds({"a": ["Council raises rates by four percent"],
                    "b": ["Council raises rates by four percent"]}):
            c.load_feeds({"RNZ": ["a", "b"]})
        self.assertEqual(len(c.headlines), 1)

    def test_one_dead_feed_does_not_lose_the_outlet(self):
        c = HeadlineCorpus()
        with feeds({"a": FeedError("HTTP 404 from a"),
                    "b": ["Health budget reallocated across districts"]}):
            c.load_feeds({"RNZ": ["a", "b"]})
        self.assertEqual(c.outlets_ok, ["RNZ"])

    def test_every_feed_dead_reports_the_reason(self):
        c = HeadlineCorpus()
        with feeds({"a": FeedError("HTTP 404 from a")}):
            c.load_feeds({"RNZ": ["a"]})
        self.assertEqual(c.outlets_ok, [])
        self.assertIn("404", c.outlets_failed[0][1])

    def test_a_plain_string_still_works(self):
        c = HeadlineCorpus()
        with feeds({"a": ["Council raises rates by four percent"]}):
            c.load_feeds({"RNZ": "a"})
        self.assertEqual(c.outlets_ok, ["RNZ"])


if __name__ == "__main__":
    unittest.main()
