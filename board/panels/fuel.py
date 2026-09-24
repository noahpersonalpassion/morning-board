"""Fuel, from MBIE's weekly monitoring CSV. No key; a plain download.

The panel that taught the board its main rule. MBIE paused parts of this
series on 22 July 2026 citing volatility, and in January revised eight months
of history after changing its population weightings. During the largest fuel
shock in recent memory, the authoritative feed went quiet and then rewrote
its own past.

So this panel checks the age of what it reads. A figure older than the
series' own weekly cadence is reported as PAUSED with its real date, never
shown as current. A number that is stale is not a smaller version of a
correct number; it is a wrong one that looks identical.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone

from notice.feeds import FeedError, fetch
from .base import Panel, PanelResult, State

CSV_URL = (
    "https://www.mbie.govt.nz/assets/Data-Files/Energy/"
    "Weekly-fuel-price-monitoring/weekly-table.csv"
)

# The series is weekly. Anything older than this is not "the latest", it is
# a source that has stopped.
STALE_AFTER_DAYS = 12

WANTED_VARIABLE = "board price"
WANTED_FUEL = "regular petrol"

# A mid-size car. Stated rather than hidden, because the dollar figure below
# is only as honest as the assumption it rests on, and a reader with a Hilux
# should be able to see the number to scale.
TANK_LITRES = 50.0


@dataclass
class FuelPanel:
    url: str = CSV_URL
    panel_id: str = "fuel"
    label: str = "Fuel"

    def render(self) -> PanelResult:
        raw = fetch(self.url, timeout=45).decode("utf-8-sig", "replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
        if not rows:
            raise FeedError("MBIE CSV was empty")

        latest = _latest_matching(rows)
        if latest is None:
            return PanelResult(
                state=State.PAUSED,
                reading="No figure",
                flag="series changed",
                note=(
                    "MBIE's CSV no longer carries the column this reads. "
                    "The format changed; nothing is shown until it is remapped."
                ),
            )

        when, value = latest
        previous = _previous_week(rows, when)
        age = (datetime.now(timezone.utc).date() - when).days

        if age > STALE_AFTER_DAYS:
            return PanelResult(
                state=State.PAUSED,
                reading="No figure",
                flag="source paused",
                note=(
                    f"MBIE last published on {when.strftime('%-d %B')}, "
                    f"{age} days ago, against a weekly cadence. Prices are "
                    f"moving; the official picture is not."
                ),
                as_of=when.isoformat(),
                meta={"age_days": age, "last_value": value},
            )

        # A price with no direction is half a fact: 320 means nothing unless
        # you know whether it is climbing. The CSV already carries the
        # history, so the comparison costs one more pass over rows we read
        # anyway.
        note = (
            f"National average board price, week ending "
            f"{when.strftime('%-d %B')}. Source: MBIE weekly fuel monitoring."
        )
        move = None
        if previous is not None:
            move = value - previous

        # Cents per litre is the unit the industry quotes in and nobody
        # thinks in. A tank is the unit you actually pay in, so the board
        # does the multiplication rather than leaving it to you at 6am.
        tank = value * TANK_LITRES / 100
        effect = f"A {TANK_LITRES:.0f}-litre tank costs about ${tank:.0f}"
        if move is not None and abs(move) >= 0.5:
            swing = abs(move) * TANK_LITRES / 100
            effect += (f" — ${swing:.0f} "
                       f"{'more' if move > 0 else 'less'} than last week.")
        elif move is not None:
            effect += ", unchanged on the week."
        else:
            effect += "."

        return PanelResult(
            state=State.LIVE,
            reading=f"{value:.0f}",
            unit="c/L regular",
            effect=effect,
            note=note,
            as_of=when.isoformat(),
            meta={"age_days": age, "week_change": move,
                  "tank_cost": round(tank, 2)},
        )


def _previous_week(rows: list[dict], latest: date) -> float | None:
    """The most recent matching value from BEFORE the latest week.

    Deliberately "the previous published week" rather than "seven days ago":
    MBIE has skipped weeks, and subtracting from a gap would invent a change
    that did not happen.
    """
    best: tuple[date, float] | None = None
    for row in rows:
        low = {(k or "").strip().lower(): (v or "").strip()
               for k, v in row.items()}
        if (WANTED_VARIABLE not in low.get("variable", "").lower()
                or WANTED_FUEL not in low.get("fuel", "").lower()):
            continue
        try:
            when = date.fromisoformat(low.get("date", "")[:10])
            value = float(low.get("value", ""))
        except (ValueError, TypeError):
            continue
        if when < latest and (best is None or when > best[0]):
            best = (when, value)
    return best[1] if best else None


def _latest_matching(rows: list[dict]) -> tuple[date, float] | None:
    """MBIE publishes long format: one row per week per variable per fuel.

    Column names have changed before and will change again, so this matches
    case-insensitively on content rather than trusting exact headers.
    """
    best: tuple[date, float] | None = None
    for row in rows:
        low = {(k or "").strip().lower(): (v or "").strip()
               for k, v in row.items()}
        variable = low.get("variable", "").lower()
        fuel = low.get("fuel", "").lower()
        if WANTED_VARIABLE not in variable or WANTED_FUEL not in fuel:
            continue
        try:
            when = date.fromisoformat(low.get("date", "")[:10])
            value = float(low.get("value", ""))
        except (ValueError, TypeError):
            continue
        if best is None or when > best[0]:
            best = (when, value)
    return best
