"""Six weeks of real Gazette notices, harvested 23 Sep 2026.

Window: 14 August - 23 September 2026 inclusive, all four useful notice
types (Departmental, General Section, Land Notices, Secondary Legislation).
Insolvency types were excluded at the search, as they will be in production.

Titles, notice numbers and dates are verbatim from gazette.govt.nz. Bodies
and region tags are absent: the search listing does not carry them, and the
site is behind bot protection, so fetching 300 individual notice pages would
have been both slow and rude. That absence is itself a finding — see the
`needs_fetch` bucket in the decision log.

This corpus answers the question v0 exists to answer: how many genuinely
novel, genuinely consequential changes reach one person per week.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..models import Candidate, Provenance

SOURCE_ID = "gazette"
SOURCE_NAME = "New Zealand Gazette"

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FILES = ["harvest_p1.txt", "harvest_p2.txt", "harvest_p3.txt"]

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_date(raw: str) -> datetime:
    """'23SEP2026' -> datetime. Day may be one or two digits."""
    raw = raw.strip()
    for cut in (2, 1):
        try:
            day = int(raw[:cut])
            mon = MONTHS[raw[cut:cut + 3].upper()]
            year = int(raw[cut + 3:cut + 7])
            return datetime(year, mon, day, tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
    raise ValueError(f"unparseable date: {raw!r}")


def collect() -> list[Candidate]:
    retrieved = datetime.now(timezone.utc)
    out: list[Candidate] = []
    seen: set[str] = set()
    for name in FILES:
        path = FIXTURES / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.count("|") < 2:
                continue
            number, raw_date, title = line.split("|", 2)
            if number in seen:
                continue
            seen.add(number)
            out.append(Candidate(
                source_id=SOURCE_ID,
                source_name=SOURCE_NAME,
                external_id=number,
                title=title.strip(),
                body="",
                url=f"https://gazette.govt.nz/notice/id/{number}",
                published=_parse_date(raw_date),
                retrieved=retrieved,
                provenance=Provenance.LIVE,
                notice_number=number,
                tags=[],
                settled_on_publication=True,
            ))
    return out
