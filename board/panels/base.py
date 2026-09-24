"""What a panel is.

The whole board rests on one rule: **a panel never raises and never lies.**
If a source is down, slow, paused by its publisher, or returns something
unrecognisable, the panel says so in its own row. It does not disappear, and
it does not quietly show yesterday's number.

That rule is enforced here rather than left to each panel's author, because
the failure mode it prevents is invisible: a stale figure looks exactly like
a current one, and a missing row looks exactly like a row with nothing to
report. Both are indistinguishable from the board working correctly, which
is the worst property a glance surface can have.

So `Panel.render()` is wrapped by `safe_render()`, which catches everything
and turns it into an UNREAD row naming the failure.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class State(str, Enum):
    """The mark in the left margin, and what it means."""

    LIVE = "live"        # read successfully, something to report
    QUIET = "quiet"      # read successfully, nothing to report. Not a failure.
    URGENT = "urgent"    # something you cannot undo is closing
    PAUSED = "paused"    # the PUBLISHER stopped publishing; not our fault
    UNREAD = "unread"    # WE could not read it today; our fault or the wire's
    OFF = "off"          # not built or not configured yet


@dataclass
class PanelResult:
    state: State
    reading: str                 # the big text: "13.2°C", "Nothing", "1 open"
    unit: str = ""               # quiet trailing text inside the reading
    note: str = ""               # the explanatory line under it
    flag: str = ""               # small chip: "source paused", "cannot undo"
    flag_kind: str = "warn"      # warn | alert
    extra_html: str = ""         # a panel may draw its own thing (the chart)
    link_label: str = ""
    link_url: str = ""
    # Panels that report a *number* carry the moment it was true. A reading
    # with no as-of is fine (a countdown); a stale one must never be shown
    # as current, so anything older than its own cadence downgrades itself.
    as_of: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_you(self) -> bool:
        return self.state in (State.URGENT,)


class Panel(Protocol):
    """One row. `panel_id` is stable; `label` is what the reader sees."""

    panel_id: str
    label: str

    def render(self) -> PanelResult: ...


def safe_render(panel: Panel) -> PanelResult:
    """Run a panel so that no failure can take the board down or hide a row.

    A panel that throws becomes an UNREAD row naming its exception class. The
    reader learns that this thing was not checked today, which is true and
    useful; the alternative — an absent row — reads identically to "nothing
    to report", which is a lie.
    """
    try:
        return panel.render()
    except Exception as exc:  # noqa: BLE001 — deliberate: no panel may escape
        return PanelResult(
            state=State.UNREAD,
            reading="Unread",
            flag="not read today",
            flag_kind="warn",
            note=(
                f"{panel.label} could not be read this morning "
                f"({type(exc).__name__}). Nothing is shown rather than "
                f"something stale."
            ),
            meta={"error": str(exc)[:200],
                  "trace": traceback.format_exc(limit=3)},
        )


def render_all(panels: list[Panel]) -> list[tuple[Panel, PanelResult]]:
    return [(p, safe_render(p)) for p in panels]
