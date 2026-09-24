"""Fine particulate in the air you are about to walk out into.

The most direct instrument on the board. Petrol costs you money next week;
this is in your lungs within the hour, and unlike the weather you cannot
look out the window and see it — PM2.5 is invisible at every level that
matters, which is exactly why a number beats a glance.

Auckland's air is usually clean, so this tile will read "low" most mornings.
That is not a wasted row. A measurement that is reliably reassuring is worth
having precisely because it makes the unusual morning legible: a still
winter inversion, smoke drifting off a scrub fire, a calm day over the
motorway. Without the ordinary readings behind it, one bad number is just a
number.

The board states the measurement against the World Health Organization's
published guideline and stops there. It does not tell anyone whether to go
outside: that depends on a person's own lungs, and this is a thermometer,
not a doctor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from notice.feeds import FeedError, fetch
from .base import Panel, PanelResult, Scale, State

API = (
    "https://air-quality-api.open-meteo.com/v1/air-quality"
    "?latitude={lat}&longitude={lon}"
    "&current=pm2_5,pm10"
    "&timezone=Pacific%2FAuckland"
)

# WHO Global Air Quality Guidelines, 2021: PM2.5 24-hour mean of 15 µg/m³,
# annual mean of 5. These are the published thresholds, not this board's
# opinion, and they are named on the page so a reader can go and check them.
WHO_ANNUAL = 5.0
WHO_DAILY = 15.0

# The top of the bar. Twice the daily guideline, so ordinary clean-air
# mornings sit low in the band and a genuinely bad day fills it rather than
# pinning silently at the end.
BAR_TOP = 30.0


@dataclass
class AirPanel:
    lat: float
    lon: float
    panel_id: str = "air"
    label: str = "Air"
    url: str = API

    def render(self) -> PanelResult:
        raw = fetch(self.url.format(lat=self.lat, lon=self.lon), timeout=25)
        data = json.loads(raw)

        current = data.get("current")
        if not isinstance(current, dict):
            raise FeedError("air-quality response had no 'current' block")

        pm25 = current.get("pm2_5")
        if pm25 is None:
            raise FeedError("air-quality response carried no pm2_5 reading")
        try:
            pm25 = float(pm25)
        except (TypeError, ValueError) as exc:
            raise FeedError(f"pm2_5 was not a number: {pm25!r}") from exc

        band, tone, effect = _read(pm25)

        return PanelResult(
            state=State.LIVE,
            reading=f"{pm25:.0f}",
            unit="µg/m³ PM2.5",
            icon="air",
            link_label="Your region's monitoring",
            link_url="https://www.lawa.org.nz/explore-data/air-quality",
            why=f"Measured this hour. The bands are the World Health "
                f"Organization's 2021 guidelines — {WHO_ANNUAL:.0f} "
                f"µg/m³ as an annual mean, {WHO_DAILY:.0f} over 24 "
                f"hours — not this board's opinion of what is clean.",
            effect=effect,
            note=(
                "Fine particulate, measured now. Source: Open-Meteo air "
                "quality, against the World Health Organization's 2021 "
                f"guidelines — {WHO_ANNUAL:.0f} µg/m³ as an annual mean, "
                f"{WHO_DAILY:.0f} over 24 hours."
            ),
            flag="" if tone == "ok" else band.lower(),
            flag_kind="warn" if tone == "warn" else "alert",
            scale=Scale(
                value=pm25, low=0.0, high=BAR_TOP,
                low_label="clean",
                mid_label=f"WHO 24h {WHO_DAILY:.0f}",
                high_label=f"{BAR_TOP:.0f}+",
                tone=tone,
            ),
            as_of=str(current.get("time", "")),
            meta={"pm2_5": pm25, "pm10": current.get("pm10"), "band": band},
        )


def _read(pm25: float) -> tuple[str, str, str]:
    """Band, tone, and the sentence a person can act on.

    Deliberately describes the air rather than the reader. "Below the WHO
    guideline" is a fact about Onehunga; "you can go for a run" is a claim
    about someone's lungs, and this panel does not know whose.
    """
    if pm25 <= WHO_ANNUAL:
        return ("Clean", "ok",
                "Well below the WHO guideline. Ordinary clean Auckland air.")
    if pm25 <= WHO_DAILY:
        return ("Low", "ok",
                "Below the WHO 24-hour guideline, in the range this city "
                "sits at most days.")
    if pm25 <= 2 * WHO_DAILY:
        return ("Raised", "warn",
                f"Above the WHO 24-hour guideline of {WHO_DAILY:.0f}. Often "
                "a still day holding smoke or traffic close to the ground.")
    return ("High", "alert",
            f"More than twice the WHO 24-hour guideline of {WHO_DAILY:.0f}. "
            "Anyone with asthma or a heart condition has reason to keep "
            "windows shut and hard exercise indoors.")
