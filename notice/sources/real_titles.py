"""Real Gazette notice metadata, captured 23 Sep 2026 for 15-23 Sep.

Titles, notice numbers, types and dates are verbatim from gazette.govt.nz.
Bodies are omitted on purpose: the plain-English effect comes from the
template table, so the pipeline has to work without one.

This is the tuning set. Run against it, read the decision log, and every
"no template for this kind of notice" line is one row to add to TEMPLATES.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..models import Candidate, Provenance

SOURCE_ID = "gazette"
SOURCE_NAME = "New Zealand Gazette"

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gazette_real_titles.json"


def collect() -> list[Candidate]:
    retrieved = datetime.now(timezone.utc)
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out: list[Candidate] = []
    for row in rows:
        if "number" not in row:      # the leading comment row
            continue
        published = datetime.fromisoformat(row["date"]).replace(
            tzinfo=timezone.utc
        )
        out.append(Candidate(
            source_id=SOURCE_ID,
            source_name=SOURCE_NAME,
            external_id=row["number"],
            title=row["title"],
            body=row.get("body", ""),
            url=f"https://gazette.govt.nz/notice/id/{row['number']}",
            published=published,
            retrieved=retrieved,
            provenance=Provenance.LIVE,
            notice_number=row["number"],
            tags=row.get("tags", []),
            settled_on_publication=True,
        ))
    return out
