"""Something happened that you would want to know before you got out of bed.

This is the closest thing the board has to breaking news, and it is built to
be the opposite of a ticker.

A news ticker is always full. It has to be, because it is a fixed piece of
furniture that would look broken if it emptied — so on a quiet day it fills
itself with whatever is nearest to hand, and the reader learns to treat it
as wallpaper. By the time something real scrolls past, the channel has spent
its credibility on nothing.

So this bar is **absent almost every day**, and its absence is the product.
When it appears, something crossed a line that a number decided.

Both feeds are GeoNet: publicly funded, no key, no editor, no framing. A
magnitude is not an opinion and an alert level is not a take. The board
prefers instruments to authors wherever an instrument exists.

Two rules learned from the data rather than assumed:

  1. **`quality` can be "deleted".** GeoNet withdraws events its automatic
     system got wrong. A withdrawn quake is not a small quake, it is one
     that did not happen, and showing it would be the board telling you the
     ground moved when it did not.

  2. **An absent bar is a claim.** "Nothing crossed a line" is only true if
     something looked. When this panel cannot read GeoNet it does not
     silently render nothing — the build drops it to an ordinary board row
     reporting that it went unread, because a quiet morning and a broken
     feed must never look identical.

  3. **Volcanic alert level is not an event.** White Island sits at level 2
     permanently and Ruapehu at 1. A rule of "alert when level >= 2" would
     have pinned a volcano warning to the top of this board forever — a
     ticker by another name. What is news is the *change*, so that is what
     this watches, with the absolute threshold kept only for level 3 and up,
     where an eruption is actually underway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt

from notice.feeds import FeedError, fetch
from .base import Panel, PanelResult, State

QUAKE_API = "https://api.geonet.org.nz/quake?MMI=4"
VOLCANO_API = "https://api.geonet.org.nz/volcano/val"

# A morning board. A quake three days ago is not something you need told at
# breakfast — you were there. The country panel can carry the aftermath.
WINDOW_HOURS = 24

# Every threshold here is a number rather than a judgement, and each one is
# stated on the page so a reader can disagree with the rule rather than
# having to trust it.
FELT_MMI, FELT_KM = 4, 120          # close enough that you probably felt it
STRONG_MMI, STRONG_KM = 6, 300      # strong enough to matter further out
NATIONAL_MAGNITUDE = 6.0            # big enough to concern the whole country

# Volcanic alert levels that speak without needing a change: 3 is "minor
# eruption", by which point it is happening, not building.
ERUPTING_LEVEL = 3
# How long a level *change* stays on the board after it happens.
CHANGE_VISIBLE_DAYS = 7

# GNS/GeoNet's own wording for the Modified Mercalli intensity felt at the
# epicentre. Quoted rather than paraphrased, and always attributed, because
# the moment this panel starts describing earthquakes in its own words it
# has become a newsroom.
MMI_WORDS = {
    3: "weak",
    4: "light",
    5: "moderate",
    6: "strong",
    7: "severe",
    8: "very severe",
    9: "violent",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Good to a few hundred metres at these scales."""
    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * r * asin(sqrt(a))


@dataclass
class Quake:
    public_id: str
    when: datetime
    magnitude: float
    mmi: int
    depth_km: float
    locality: str
    distance_km: float

    @property
    def why(self) -> str:
        """Which rule let this through. Shown, so the rule is auditable."""
        if self.magnitude >= NATIONAL_MAGNITUDE:
            return f"magnitude {NATIONAL_MAGNITUDE} or above, anywhere in New Zealand"
        if self.mmi >= STRONG_MMI and self.distance_km <= STRONG_KM:
            return f"intensity {STRONG_MMI} or above within {STRONG_KM} km"
        return f"intensity {FELT_MMI} or above within {FELT_KM} km"


def qualifies(q: Quake) -> bool:
    if q.magnitude >= NATIONAL_MAGNITUDE:
        return True
    if q.mmi >= STRONG_MMI and q.distance_km <= STRONG_KM:
        return True
    return q.mmi >= FELT_MMI and q.distance_km <= FELT_KM


def parse_quakes(payload: dict, lat: float, lon: float,
                 now: datetime | None = None) -> list[Quake]:
    """GeoJSON to the quakes that reach this reader, newest first.

    Withdrawn events are dropped here rather than filtered later, so no
    downstream code can accidentally resurrect one.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    out: list[Quake] = []

    for f in payload.get("features", []):
        p = f.get("properties") or {}
        if (p.get("quality") or "").lower() == "deleted":
            continue
        try:
            when = datetime.fromisoformat(str(p["time"]).replace("Z", "+00:00"))
            coords = f["geometry"]["coordinates"]
            q = Quake(
                public_id=str(p.get("publicID", "")),
                when=when,
                magnitude=float(p["magnitude"]),
                mmi=int(p["mmi"]),
                depth_km=float(p.get("depth") or 0.0),
                locality=str(p.get("locality", "")),
                distance_km=haversine_km(lat, lon,
                                         float(coords[1]), float(coords[0])),
            )
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if when < cutoff:
            continue
        if qualifies(q):
            out.append(q)

    return sorted(out, key=lambda q: q.when, reverse=True)


def parse_volcanoes(payload: dict) -> dict[str, tuple[str, int, str]]:
    """{volcanoID: (title, level, activity)}."""
    out: dict[str, tuple[str, int, str]] = {}
    for f in payload.get("features", []):
        p = f.get("properties") or {}
        vid = str(p.get("volcanoID") or "")
        if not vid:
            continue
        try:
            out[vid] = (str(p.get("volcanoTitle") or vid),
                        int(p.get("level")),
                        str(p.get("activity") or ""))
        except (TypeError, ValueError):
            continue
    return out


def volcano_alerts(
    now_levels: dict[str, tuple[str, int, str]],
    previous: dict[str, int],
    changed_on: dict[str, str],
    today: str,
) -> tuple[list[str], dict[str, str]]:
    """Which volcanoes are worth saying something about, and when each moved.

    Returns the sentences plus an updated changed-on map to carry into the
    next build. A volcano whose level is unchanged keeps the date it last
    moved, so a change stays visible for a week rather than for one build —
    an alert that appears and vanishes inside a day is one you will miss.
    """
    lines: list[str] = []
    moved = dict(changed_on)

    for vid, (title, level, activity) in sorted(now_levels.items()):
        was = previous.get(vid)
        if was is not None and was != level:
            moved[vid] = today

        recent = _within(moved.get(vid, ""), today, CHANGE_VISIBLE_DAYS)

        if level >= ERUPTING_LEVEL:
            lines.append(f"{title} is at volcanic alert level {level}. "
                         f"{activity}")
        elif recent and was is not None and was != level:
            direction = "raised" if level > was else "lowered"
            lines.append(f"{title} has been {direction} from volcanic alert "
                         f"level {was} to {level}. {activity}")
        elif recent and level >= 1:
            lines.append(f"{title} remains at volcanic alert level {level}, "
                         f"changed within the last week. {activity}")

    return lines, moved


def _within(iso_day: str, today: str, days: int) -> bool:
    if not iso_day:
        return False
    try:
        then = datetime.fromisoformat(iso_day).date()
        now = datetime.fromisoformat(today).date()
    except ValueError:
        return False
    return 0 <= (now - then).days <= days


@dataclass
class AlertPanel:
    """The bar. QUIET on a normal day, which is almost every day."""

    lat: float
    lon: float
    place: str = "here"
    previous: dict = field(default_factory=dict)
    panel_id: str = "alert"
    label: str = "Alert"
    quake_url: str = QUAKE_API
    volcano_url: str = VOLCANO_API

    def render(self) -> PanelResult:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        quakes = parse_quakes(
            json.loads(fetch(self.quake_url, timeout=30)),
            self.lat, self.lon, now,
        )

        # A failure here must not lose the quakes, which are the half of this
        # panel most likely to matter. Volcanic levels move over weeks; a
        # quake is minutes old.
        vol_lines: list[str] = []
        moved: dict[str, str] = dict(self.previous.get("changed_on") or {})
        levels: dict[str, int] = {}
        try:
            now_levels = parse_volcanoes(
                json.loads(fetch(self.volcano_url, timeout=30))
            )
            levels = {k: v[1] for k, v in now_levels.items()}
            vol_lines, moved = volcano_alerts(
                now_levels,
                dict(self.previous.get("levels") or {}),
                moved,
                today,
            )
        except (FeedError, ValueError, KeyError):
            vol_lines = []

        carry = {"levels": levels, "changed_on": moved}

        if not quakes and not vol_lines:
            return PanelResult(
                state=State.QUIET,
                reading="Nothing",
                note=(
                    "No earthquake near you and no change in volcanic alert "
                    "level in the last day. This bar is empty most mornings; "
                    "that is what it is for."
                ),
                meta=carry,
            )

        head, effect, detail = self._say(quakes, vol_lines)
        return PanelResult(
            state=State.URGENT,
            reading=head,
            effect=effect,
            note=detail,
            flag="geonet",
            flag_kind="alert",
            link_label="GeoNet",
            link_url="https://www.geonet.org.nz/",
            as_of=now.isoformat(),
            meta={**carry, "quakes": [q.public_id for q in quakes]},
        )

    def _say(self, quakes: list[Quake], vol_lines: list[str]):
        if quakes:
            q = quakes[0]
            near = f"{q.distance_km:.0f} km away"
            word = MMI_WORDS.get(q.mmi, "")
            shaking = f" — {word} shaking at the epicentre" if word else ""

            effect = (
                f"{q.locality}, {q.distance_km:.0f} km from {self.place}. "
                f"GeoNet rates the shaking where it struck as intensity "
                f"{q.mmi}{',' if word else ''} {word}."
            )
            detail = (
                f"Magnitude {q.magnitude:.1f}, {q.depth_km:.0f} km deep, at "
                f"{q.when.astimezone().strftime('%-I:%M%p').lower()}. "
                f"Shown because it met the rule: {q.why}."
            )
            if len(quakes) > 1:
                detail += f" {len(quakes) - 1} more in the last day."
            if vol_lines:
                detail += " " + " ".join(vol_lines)
            return f"M{q.magnitude:.1f}", effect, detail

        return ("Volcano", vol_lines[0],
                " ".join(vol_lines[1:]) + " Source: GeoNet volcanic alert "
                "levels, which are set by duty volcanologists, not by us.")
