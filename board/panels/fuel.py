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

        return PanelResult(
            state=State.LIVE,
            reading=f"{value:.0f}",
            unit="c/L regular",
            note=(
                f"National average board price, week ending "
                f"{when.strftime('%-d %B')}."
            ),
            as_of=when.isoformat(),
            meta={"age_days": age},
        )


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
