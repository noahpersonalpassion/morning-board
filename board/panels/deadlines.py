"""Deadlines: a permanent row with temporary occupants.

The design note that produced this: enrolment is not a category, it is an
occupant. A row per *thing* means the board grows a row for every deadline
and keeps it forever; a row per *kind of thing* means Deadlines holds
enrolment until 25 October, then holds a consultation closing in December,
then says "None open" and goes quiet.

Only things you cannot undo belong here. A deadline you can miss and fix
later is not a deadline, it is a reminder, and it does not earn a row on a
board someone reads for twenty seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .base import Panel, PanelResult, State


@dataclass
class Deadline:
    name: str
    closes: date
    why: str                      # what happens if you miss it
    link_label: str = ""
    link_url: str = ""
    # How many days out it starts appearing. A year-long countdown is noise.
    visible_within_days: int = 60


@dataclass
class DeadlinesPanel:
    deadlines: list[Deadline] = field(default_factory=list)
    panel_id: str = "deadlines"
    label: str = "Deadlines"

    def render(self) -> PanelResult:
        today = datetime.now(timezone.utc).date()

        live = sorted(
            (d for d in self.deadlines
             if 0 <= (d.closes - today).days <= d.visible_within_days),
            key=lambda d: d.closes,
        )

        if not live:
            return PanelResult(
                state=State.QUIET,
                reading="None open",
                note=(
                    "Nothing is closing that you cannot reopen later. "
                    "This row fills itself when something is."
                ),
            )

        first = live[0]
        days = (first.closes - today).days
        closing_word = "today" if days == 0 else (
            "tomorrow" if days == 1 else f"{days} days"
        )

        note = (
            f"{first.name} closes {first.closes.strftime('%A %-d %B')} "
            f"\u2014 {closing_word}. {first.why}"
        )
        if len(live) > 1:
            nxt = live[1]
            note += (
                f" Then {nxt.name}, "
                f"{(nxt.closes - today).days} days out."
            )

        return PanelResult(
            state=State.URGENT,
            reading=str(len(live)),
            unit="open" if len(live) > 1 else "open",
            flag="cannot undo",
            flag_kind="alert",
            note=note,
            link_label=first.link_label,
            link_url=first.link_url,
            meta={"days": days, "count": len(live)},
        )


def default_deadlines() -> list[Deadline]:
    """Seeded with the one real, verified deadline.

    Enrolment closes at midnight at the end of Sunday 25 October 2026, so the
    last full day it is open is the 25th. Verified against vote.nz.
    """
    return [
        Deadline(
            name="Enrolment",
            closes=date(2026, 10, 25),
            why="Advance voting opens the next morning and you cannot enrol once it does.",
            link_label="Check your enrolment",
            link_url="https://vote.nz",
            visible_within_days=90,
        ),
    ]
