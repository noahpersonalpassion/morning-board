"""Sun times, the daily change in them, and the UV peak.

This row exists because of a design problem, not a data one. Most mornings
Near You says Nothing, Deadlines says None open, and Fuel moves a cent. A
board where nothing ever changes is a board nobody opens — but the fix is
not to manufacture movement, it is to include something that genuinely
changes every single day and that people like knowing.

Daylight does that. "Two minutes more than yesterday" is different every
morning, true without interpretation, and in September in New Zealand it is
the fact the whole country is quietly keeping track of anyway.

UV rides along because it belongs to the same object — the sun today — and
because New Zealand's UV is both genuinely dangerous and genuinely easy to
forget. It only speaks up when it is worth acting on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from notice.feeds import FeedError, fetch
from .base import Panel, PanelResult, State

API = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&daily=sunrise,sunset,uv_index_max"
    "&timezone=Pacific%2FAuckland&past_days=1&forecast_days=1"
)

# Below this the advice is "nothing special"; at or above it, shade matters.
UV_WORTH_SAYING = 6

# Daylight is measured from here, not from midnight: five o'clock is when
# the question "is there still light?" starts having a practical answer.
AFTER_WORK_FROM = 17

# Roughly minutes of unprotected exposure before a fair skin burns. NIWA's
# public guidance rounds to these; they are indicative, not medical.
UV_BURN_MINUTES = {11: 10, 8: 15, 6: 25, 3: 45}


@dataclass
class DaylightPanel:
    lat: float
    lon: float
    panel_id: str = "daylight"
    label: str = "Daylight"

    def render(self) -> PanelResult:
        raw = fetch(API.format(lat=self.lat, lon=self.lon), timeout=20)
        d = json.loads(raw)["daily"]

        # past_days=1 means index 0 is yesterday and index 1 is today.
        if len(d["sunset"]) < 2:
            raise FeedError("open-meteo returned no comparison day")

        y_set = _parse(d["sunset"][0])
        t_rise, t_set = _parse(d["sunrise"][1]), _parse(d["sunset"][1])
        uv = d.get("uv_index_max", [None, None])[1]

        # Compare clock times, not instants: the interesting number is
        # "sunset is later than it was", which is what a person notices.
        delta = round(
            (t_set.hour * 60 + t_set.minute) - (y_set.hour * 60 + y_set.minute)
        )

        note = (f"Sunrise {_clock(t_rise)}, sunset {_clock(t_set)}. "
                f"{_delta_phrase(delta)} Source: Open-Meteo, computed "
                f"astronomically rather than observed.")
        flag, kind = "", "warn"
        effect = _after_work(t_set)
        if uv is not None and uv >= UV_WORTH_SAYING:
            burn = next((m for t, m in UV_BURN_MINUTES.items() if uv >= t), 60)
            effect += (f" UV peaks at {uv:.0f} — unprotected fair skin burns "
                       f"in about {burn} minutes.")
            flag, kind = f"uv {uv:.0f}", "warn" if uv < 8 else "alert"

        return PanelResult(
            state=State.LIVE,
            reading=_clock(t_set),
            unit="sunset",
            flag=flag,
            flag_kind=kind,
            effect=effect,
            note=note,
            as_of=d["sunset"][1],
            meta={"sunrise": d["sunrise"][1], "sunset": d["sunset"][1],
                  "delta_minutes": delta, "uv_max": uv},
        )


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _clock(dt: datetime) -> str:
    """7:42pm, not 19:42 — this is a sentence, not a timetable."""
    hour = dt.hour % 12 or 12
    suffix = "am" if dt.hour < 12 else "pm"
    return f"{hour}:{dt.minute:02d}{suffix}"


def _after_work(sunset: datetime) -> str:
    """Daylight expressed as the thing people actually plan with.

    "Sunset 6:18pm" is a fact about the sun. "An hour and a quarter of light
    after five" is a fact about your evening, and it is the same fact — just
    measured from the moment a reader cares about rather than from noon.
    """
    minutes = (sunset.hour * 60 + sunset.minute) - AFTER_WORK_FROM * 60
    if minutes <= 0:
        return "Dark before five."
    if minutes < 60:
        return f"About {minutes} minutes of light after five."

    hours, rest = divmod(minutes, 60)
    quarter = 15 * round(rest / 15)
    if quarter == 60:
        hours, quarter = hours + 1, 0
    # "1 and a quarter hours" is what a calculator says. A person says "an
    # hour and a quarter" — and the fraction takes the plural only when it
    # trails the noun, so it is "three quarters" after "an hour" but "three
    # quarter" before "hours".
    if hours == 1:
        tail = {0: "", 15: " and a quarter", 30: " and a half",
                45: " and three quarters"}[quarter]
        return f"About an hour{tail} of light after five."

    tail = {0: "", 15: " and a quarter", 30: " and a half",
            45: " and three quarter"}[quarter]
    spoken = {2: "two", 3: "three", 4: "four", 5: "five",
              6: "six", 7: "seven"}.get(hours, str(hours))
    return f"About {spoken}{tail} hours of light after five."


def _delta_phrase(minutes: int) -> str:
    if minutes == 0:
        return "The same as yesterday."
    word = "later" if minutes > 0 else "earlier"
    n = abs(minutes)
    unit = "minute" if n == 1 else "minutes"
    return f"{n} {unit} {word} than yesterday."
