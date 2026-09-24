"""The alert bar's rules.

Every fixture here is a real GeoNet record with only the timestamp changed,
so these tests check the parser against the shapes the feed actually emits
rather than against shapes convenient to write.

The most important test in the file is `test_steady_white_island_is_silent`.
White Island sits at volcanic alert level 2 permanently; a naive threshold
would put a volcano warning at the top of this board every single morning
forever, which is exactly the failure the bar exists to avoid.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from board.panels.alerts import (  # noqa: E402
    haversine_km, parse_quakes, parse_volcanoes, volcano_alerts,
)

# Onehunga, from reader.json.
HERE = (-36.9333, 174.7833)

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)


def quake(lat, lon, mag, mmi, hours_ago, quality="best", locality="somewhere"):
    when = NOW - timedelta(hours=hours_ago)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "publicID": f"t{int(mag * 100)}{int(hours_ago)}",
            "time": when.isoformat().replace("+00:00", "Z"),
            "depth": 10.0, "magnitude": mag, "mmi": mmi,
            "locality": locality, "quality": quality,
        },
    }


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


class TestDistance(unittest.TestCase):
    def test_known_distance(self):
        # Onehunga to Wellington is about 470 km great-circle.
        km = haversine_km(*HERE, -41.2866, 174.7756)
        self.assertTrue(460 < km < 490, km)

    def test_zero(self):
        self.assertAlmostEqual(haversine_km(*HERE, *HERE), 0.0, places=6)


class TestQuakes(unittest.TestCase):
    def test_withdrawn_quake_never_appears(self):
        """GeoNet's `quality: deleted` means the event did not happen.

        Showing one would be the board telling a reader the ground moved
        when it did not — the single worst thing this panel could do.
        """
        payload = collection(
            quake(-37.2, 175.0, 3.5, 4, 2, quality="deleted",
                  locality="20 km south-east of Auckland")
        )
        self.assertEqual(parse_quakes(payload, *HERE, NOW), [])

    def test_small_quake_close_by_is_felt(self):
        payload = collection(
            quake(-37.2, 175.0, 3.5, 4, 2, locality="near Auckland")
        )
        got = parse_quakes(payload, *HERE, NOW)
        self.assertEqual(len(got), 1)
        self.assertLess(got[0].distance_km, 120)

    def test_moderate_quake_far_away_is_not(self):
        """M4.9 intensity 5 at Paraparaumu: real, and not Auckland's problem.

        This is the rule doing its job. The quake was genuinely newsworthy
        in Wellington and genuinely irrelevant here, and a board that showed
        it would be a national news feed wearing a local badge.
        """
        payload = collection(
            quake(-40.74394989, 174.684295654, 4.929, 5, 3,
                  locality="30 km north-west of Paraparaumu")
        )
        self.assertEqual(parse_quakes(payload, *HERE, NOW), [])

    def test_severe_quake_at_range_reaches_you(self):
        """The real M5.9 intensity 7 at Taumarunui, ~230 km from Onehunga."""
        payload = collection(
            quake(-38.965606689, 175.2371521, 5.947, 7, 4,
                  locality="5 km south of Taumarunui")
        )
        got = parse_quakes(payload, *HERE, NOW)
        self.assertEqual(len(got), 1)
        self.assertIn("intensity 6 or above", got[0].why)

    def test_big_quake_anywhere_reaches_everyone(self):
        """The real M6.3 near Milford Sound: 1,000 km away and still yours.

        Past magnitude 6 the question stops being whether you felt it.
        """
        payload = collection(
            quake(-45.006168365, 167.584609985, 6.329, 6, 5,
                  locality="45 km south-west of Milford Sound")
        )
        got = parse_quakes(payload, *HERE, NOW)
        self.assertEqual(len(got), 1)
        self.assertGreater(got[0].distance_km, 900)
        self.assertIn("anywhere in New Zealand", got[0].why)

    def test_yesterdays_quake_has_expired(self):
        payload = collection(quake(-37.2, 175.0, 3.5, 4, 30))
        self.assertEqual(parse_quakes(payload, *HERE, NOW), [])

    def test_newest_first(self):
        payload = collection(
            quake(-37.2, 175.0, 3.5, 4, 8),
            quake(-37.1, 174.9, 3.6, 4, 1),
        )
        got = parse_quakes(payload, *HERE, NOW)
        self.assertEqual([round(q.magnitude, 1) for q in got], [3.6, 3.5])

    def test_malformed_feature_is_skipped_not_fatal(self):
        payload = {"features": [
            {"geometry": {}, "properties": {"time": "nonsense"}},
            quake(-37.2, 175.0, 3.5, 4, 1),
        ]}
        self.assertEqual(len(parse_quakes(payload, *HERE, NOW)), 1)


# Real levels from the live feed on 24 September 2026.
LIVE_VOLCANOES = collection(
    {"geometry": {"coordinates": [177.183, -37.521]},
     "properties": {"volcanoID": "whiteisland", "volcanoTitle": "White Island",
                    "level": 2, "acc": "Yellow",
                    "activity": "Moderate to heightened volcanic unrest."}},
    {"geometry": {"coordinates": [175.563, -39.281]},
     "properties": {"volcanoID": "ruapehu", "volcanoTitle": "Ruapehu",
                    "level": 1, "acc": "Green",
                    "activity": "Minor volcanic unrest."}},
    {"geometry": {"coordinates": [175.896, -38.784]},
     "properties": {"volcanoID": "taupo", "volcanoTitle": "Taupo",
                    "level": 0, "acc": "Green",
                    "activity": "No volcanic unrest."}},
)

TODAY = "2026-09-24"


class TestVolcanoes(unittest.TestCase):
    def test_parses_live_feed(self):
        got = parse_volcanoes(LIVE_VOLCANOES)
        self.assertEqual(got["whiteisland"][1], 2)
        self.assertEqual(got["ruapehu"][1], 1)

    def test_steady_white_island_is_silent(self):
        """The test this panel was redesigned around.

        White Island has been at level 2 for years. If a steady level 2 can
        raise the bar, the bar is raised every morning forever and the reader
        stops seeing it — at which point it is worthless on the morning it
        matters.
        """
        lines, _ = volcano_alerts(
            parse_volcanoes(LIVE_VOLCANOES),
            {"whiteisland": 2, "ruapehu": 1, "taupo": 0},
            {}, TODAY,
        )
        self.assertEqual(lines, [])

    def test_a_raised_level_speaks(self):
        lines, moved = volcano_alerts(
            parse_volcanoes(LIVE_VOLCANOES),
            {"whiteisland": 2, "ruapehu": 0, "taupo": 0},
            {}, TODAY,
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("Ruapehu", lines[0])
        self.assertIn("raised", lines[0])
        self.assertEqual(moved["ruapehu"], TODAY)

    def test_a_lowered_level_speaks_too(self):
        lines, _ = volcano_alerts(
            parse_volcanoes(LIVE_VOLCANOES),
            {"whiteisland": 3, "ruapehu": 1, "taupo": 0},
            {}, TODAY,
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("lowered", lines[0])

    def test_a_change_stays_visible_for_a_week(self):
        """An alert that appears and vanishes inside a day is one you miss."""
        lines, _ = volcano_alerts(
            parse_volcanoes(LIVE_VOLCANOES),
            {"whiteisland": 2, "ruapehu": 1, "taupo": 0},
            {"ruapehu": "2026-09-21"}, TODAY,
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("Ruapehu", lines[0])

    def test_a_change_expires(self):
        lines, _ = volcano_alerts(
            parse_volcanoes(LIVE_VOLCANOES),
            {"whiteisland": 2, "ruapehu": 1, "taupo": 0},
            {"ruapehu": "2026-08-01"}, TODAY,
        )
        self.assertEqual(lines, [])

    def test_an_eruption_speaks_without_a_change(self):
        erupting = collection(
            {"geometry": {"coordinates": [175.563, -39.281]},
             "properties": {"volcanoID": "ruapehu", "volcanoTitle": "Ruapehu",
                            "level": 3, "activity": "Minor eruption."}},
        )
        lines, _ = volcano_alerts(parse_volcanoes(erupting),
                                  {"ruapehu": 3}, {}, TODAY)
        self.assertEqual(len(lines), 1)
        self.assertIn("level 3", lines[0])

    def test_first_ever_build_says_nothing(self):
        """No previous levels means no change is knowable — not that one happened."""
        lines, _ = volcano_alerts(parse_volcanoes(LIVE_VOLCANOES), {}, {}, TODAY)
        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
