"""Weather, from Open-Meteo. No API key, no account, free for non-commercial use.

Draws its own week strip: seven bars on one temperature scale, low to high,
today in the accent colour. Only one rain figure is labelled — the wettest
day, and only when it is worth acting on. Seven rain percentages would be
seven numbers to read and no signal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from notice.feeds import fetch
from .base import Panel, PanelResult, Scale, State

API = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,weather_code"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&timezone=Pacific%2FAuckland&forecast_days=7"
)

# WMO weather codes, collapsed to words a person uses.
CONDITIONS = {
    0: "clear", 1: "mostly clear", 2: "part cloud", 3: "overcast",
    45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "freezing rain", 71: "snow", 73: "snow", 75: "snow",
    80: "showers", 81: "showers", 82: "heavy showers",
    95: "thunder", 96: "thunder", 99: "thunder",
}

# A rain chance only earns a label when it changes what you do.
RAIN_LABEL_THRESHOLD = 40


@dataclass
class WeatherPanel:
    lat: float
    lon: float
    panel_id: str = "weather"
    label: str = "Weather"

    def render(self) -> PanelResult:
        raw = fetch(API.format(lat=self.lat, lon=self.lon), timeout=20)
        data = json.loads(raw)

        now = data["current"]
        temp = now["temperature_2m"]
        cond = CONDITIONS.get(now.get("weather_code"), "")

        d = data["daily"]
        days = list(zip(d["time"], d["temperature_2m_max"],
                        d["temperature_2m_min"],
                        d["precipitation_probability_max"]))

        # Today's own low and high are the only band a current temperature
        # belongs on. A fixed 0\u201330 scale would put a New Zealand spring
        # morning near the bottom of every tile all year and say nothing.
        _, high, low, _ = days[0]

        return PanelResult(
            state=State.LIVE,
            reading=f"{temp:.1f}\u00b0C",
            unit=f"{cond} now" if cond else "now",
            icon="weather",
            why="Open-Meteo forecast for your coordinates, read at build "
                "time. The bar runs between today's own forecast low and "
                "high, not a fixed scale, so a spring morning is not "
                "pinned to the bottom of the tile all year.",
            effect=self._summary(days),
            note="Source: Open-Meteo. Bars are daily highs on one scale; "
                 "blue figures are millimetres of rain.",
            scale=Scale(value=float(temp), low=float(low), high=float(high),
                        low_label=f"{low:.0f}\u00b0 low",
                        mid_label="today",
                        high_label=f"{high:.0f}\u00b0 high"),
            extra_html=week_strip(days),
            as_of=now.get("time", ""),
            meta={"days": len(days), "low": low, "high": high},
        )

    def _summary(self, days) -> str:
        """The weather, in weather words.

        The first sentence is lifted into the page's lede, so it has to say
        something about the weather. An earlier version opened with "Bars run
        low to high" — an instruction for reading the chart — and the top of
        the board read "Bars run low to high. 1 deadline open," which is a
        caption where a forecast should be. The chart labels every bar with
        the high it reaches, so it needs no caption at all.

        Naming every wet day is no better: four day names is a list to parse,
        not a fact to absorb. Past two, the useful sentence is "most days".
        """
        wet = [_day_name(t) for t, _, _, p in days if (p or 0) >= RAIN_LABEL_THRESHOLD]
        lows = [lo for _, _, lo, _ in days]
        tail = f"Overnight lows {min(lows):.0f} to {max(lows):.0f}\u00b0C."

        if not wet:
            return f"Dry all week. {tail}"
        if len(wet) == 1:
            return f"Rain on {wet[0]}. {tail}"
        if len(wet) == 2:
            return f"Rain on {wet[0]} and {wet[1]}. {tail}"
        if len(wet) >= len(days) - 1:
            return f"Rain almost every day. {tail}"
        return f"Rain most days, from {wet[0]}. {tail}"


def _day_name(iso: str) -> str:
    from datetime import date
    y, m, dd = (int(x) for x in iso.split("-"))
    return date(y, m, dd).strftime("%A")


def week_strip(days) -> str:
    """Seven bars on ONE temperature scale, drawn to fit any range.

    The scale is computed from the week's own min and max with a degree of
    padding, so a mild week and a freezing week both fill the box; every bar
    is labelled with the high it reaches, which keeps each mark honest.
    """
    if not days:
        return ""

    highs = [hi for _, hi, _, _ in days]
    lows = [lo for _, _, lo, _ in days]
    top, bottom = max(highs) + 1, min(lows) - 1
    span = max(top - bottom, 1)

    W, H = 364, 100
    left, right = 12, 352
    y_top, y_bottom = 20, 62
    col = (right - left) / len(days)

    def y(t: float) -> float:
        return y_bottom - (t - bottom) * ((y_bottom - y_top) / span)

    bars, labels = [], []
    wettest = max(range(len(days)), key=lambda i: days[i][3] or 0)
    wet_pct = days[wettest][3] or 0

    for i, (iso, hi, lo, _pct) in enumerate(days):
        cx = left + col * i + col / 2
        y_hi, y_lo = y(hi), y(lo)
        fill = "var(--accent)" if i == 0 else "var(--bar)"
        bars.append(
            f'<rect x="{cx - 3:.0f}" y="{y_hi:.1f}" width="6" '
            f'height="{max(y_lo - y_hi, 3):.1f}" rx="3" fill="{fill}"></rect>'
        )
        cls = "wk-high now" if i == 0 else "wk-high"
        labels.append(
            f'<text class="{cls}" x="{cx:.0f}" y="{y_hi - 6:.0f}">{hi:.0f}</text>'
        )
        day = "TODAY" if i == 0 else _day_name(iso)[:3].upper()
        dcls = "wk-day now" if i == 0 else "wk-day"
        labels.append(f'<text class="{dcls}" x="{cx:.0f}" y="78">{day}</text>')

    if wet_pct >= RAIN_LABEL_THRESHOLD:
        cx = left + col * wettest + col / 2
        labels.append(
            f'<text class="wk-rain" x="{cx:.0f}" y="93">{wet_pct:.0f}% rain</text>'
        )

    alt = (
        f"Seven day outlook. Highs {min(highs):.0f} to {max(highs):.0f} degrees, "
        f"lows {min(lows):.0f} to {max(lows):.0f}."
    )
    return (
        f'<div class="week"><svg viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="{alt}"><g>{"".join(bars)}</g>'
        f'<g text-anchor="middle">{"".join(labels)}</g></svg></div>'
    )
