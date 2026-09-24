"""Loading a reader, and proving the board is not Auckland-shaped.

The important test here is test_works_anywhere: the same corpus, three
different readers, no suburb database anywhere in the path.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from notice.reader import ReaderConfigError, load  # noqa: E402
from notice.places import Proximity  # noqa: E402

GOOD = {
    "name": "Morning Board", "place": "Whitby",
    "lat": -41.1225, "lon": 174.8969,
    "region": "wellington",
    "suburbs": ["Whitby", "Paremata"],
    "streets": ["Albatross Close"],
    "proximity_floor": "SUBURB",
    "attributes": ["household"],
}


def write(data) -> str:
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(data, fh)
    fh.close()
    return fh.name


class TestLoad(unittest.TestCase):
    def test_loads(self):
        r = load(write(GOOD))
        self.assertEqual(r.place, "Whitby")
        self.assertIn("wellington", r.profile.region_terms)
        self.assertEqual(r.profile.proximity_floor, Proximity.SUBURB)

    def test_repo_config_is_valid(self):
        """The committed reader.json must always load — it is the example
        every fork starts from."""
        r = load(Path(__file__).resolve().parents[1] / "reader.json")
        self.assertTrue(r.profile.suburbs)

    def test_bad_region_names_the_options(self):
        bad = dict(GOOD, region="welligton")
        with self.assertRaises(ReaderConfigError) as ctx:
            load(write(bad))
        self.assertIn("wellington", str(ctx.exception))

    def test_unknown_attribute_is_an_error_not_a_warning(self):
        """An unrecognised attribute silently hides notices forever, which
        looks exactly like a quiet suburb."""
        bad = dict(GOOD, attributes=["household", "dairy_farmer"])
        with self.assertRaises(ReaderConfigError) as ctx:
            load(write(bad))
        self.assertIn("dairy_farmer", str(ctx.exception))

    def test_suburb_floor_without_suburbs_is_caught(self):
        bad = dict(GOOD, suburbs=[])
        with self.assertRaises(ReaderConfigError) as ctx:
            load(write(bad))
        self.assertIn("REGION", str(ctx.exception))

    def test_bad_json_says_where(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        fh.write('{"region": "wellington",}')
        fh.close()
        with self.assertRaises(ReaderConfigError) as ctx:
            load(fh.name)
        self.assertIn("line", str(ctx.exception))


class TestWorksAnywhere(unittest.TestCase):
    """Same notices, different readers, no national suburb list."""

    def setUp(self):
        from notice.novelty import HeadlineCorpus
        from notice.sources import harvest
        root = Path(__file__).resolve().parents[1]
        self.corpus = HeadlineCorpus()
        self.corpus.load_fixture(root / "fixtures" / "headlines_synthetic.json")
        self.candidates = harvest.collect()

    def local_for(self, cfg) -> list:
        from notice.delta import build_card, evaluate
        r = load(write(cfg))
        out = []
        for c in self.candidates:
            crit = evaluate(c, r.profile, self.corpus)
            if not all(x.passed for x in crit):
                continue
            try:
                card = build_card(c, crit, r.profile.attributes)
            except ValueError:
                continue
            if "nationwide" not in card.why_you:
                out.append(card)
        return out

    def test_wellington_reader_finds_its_own_street(self):
        cards = self.local_for(GOOD)
        self.assertTrue(cards)
        self.assertTrue(any("Albatross Close" in c.what for c in cards))

    def test_auckland_reader_does_not_see_wellington(self):
        akl = dict(GOOD, region="auckland", place="Onehunga",
                   suburbs=["Onehunga", "Mount Roskill"],
                   streets=["Gerrard Besson Place"])
        cards = self.local_for(akl)
        self.assertTrue(cards)
        self.assertFalse(any("Albatross" in c.what or "Rahui" in c.what
                             for c in cards))

    def test_rate_follows_what_is_happening_nearby(self):
        """Otaki has an expressway being built through it, so land is being
        taken street by street. The rate is not a constant of the product,
        it is a function of the reader's address."""
        otaki = dict(GOOD, place="Otaki",
                     suburbs=["Otaki", "Peka Peka"], streets=["Rahui Road"])
        quiet = self.local_for(GOOD)
        busy = self.local_for(otaki)
        self.assertGreater(len(busy), len(quiet) * 3)
