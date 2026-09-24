"""Core types.

A Candidate is anything a source emitted. A Card is a Candidate that passed
the Delta Rule. A Decision records what happened to a Candidate and why —
that log is the whole point of v0.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Any


class Provenance(str, Enum):
    """How much the source currently stands behind this value."""

    LIVE = "live"
    STALE = "stale"        # source is late relative to its own cadence
    PAUSED = "paused"      # source has announced it stopped publishing
    REVISED = "revised"    # source has restated past values


@dataclass
class Candidate:
    """Anything a source emitted, before judgement."""

    source_id: str              # "gazette", "legislation", "mbie_fuel"
    source_name: str            # human name for the card
    external_id: str            # stable id from the source
    title: str
    body: str
    url: str
    published: datetime
    retrieved: datetime
    provenance: Provenance = Provenance.LIVE
    # Gazette notice number, e.g. "2026-ln5366". Its two letters are the
    # notice type, which is why type filtering costs nothing.
    notice_number: str = ""
    # True when publication in this source IS the legal act. A Gazette notice
    # is not a report that something will happen — it is the instrument that
    # makes it happen, and most take effect "on the date of publication hereof
    # in the New Zealand Gazette". For such a source, settlement is presumed
    # and only explicit proposal language overrides it.
    settled_on_publication: bool = False
    # Structured tags from the notice page: Act, subject, agency, and the
    # region where geography is relevant ("Auckland"). Region matching reads
    # these rather than searching the text.
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Stable dedupe key across runs."""
        return hashlib.sha256(
            f"{self.source_id}:{self.external_id}".encode()
        ).hexdigest()[:16]

    def text(self) -> str:
        return f"{self.title}\n{self.body}"


@dataclass
class CriterionResult:
    """One of the four tests, with its reason. Never a bare bool."""

    name: str
    passed: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    """The audit record. One per candidate per run."""

    key: str
    run_date: date
    source_id: str
    title: str
    url: str
    shipped: bool
    criteria: list[CriterionResult]
    card: dict[str, Any] | None = None

    @property
    def failed_on(self) -> str | None:
        for c in self.criteria:
            if not c.passed:
                return c.name
        return None

    def to_json(self) -> str:
        d = asdict(self)
        d["run_date"] = self.run_date.isoformat()
        return json.dumps(d, default=str, ensure_ascii=False)


@dataclass
class Card:
    """What a reader sees. Every field is mandatory except `action`.

    A card that cannot fill these does not ship — that rule is enforced in
    build_card(), not left to the template.
    """

    what: str            # the change, one sentence
    effect: str          # who it lands on, and the number or date
    when: str            # effective date or closing deadline
    source_name: str
    source_url: str
    published: datetime
    retrieved: datetime
    provenance: Provenance
    confidence: str      # "Exact. Stated in the source." or a band + basis
    why_you: str         # the rule that selected this, in plain words
    action_label: str | None = None
    action_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        d["published"] = self.published.isoformat()
        d["retrieved"] = self.retrieved.isoformat()
        return d
