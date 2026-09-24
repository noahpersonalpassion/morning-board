"""Offline source so the pipeline runs before any API key arrives.

Reads fixtures/gazette_synthetic.xml. The notices in it are invented —
see the comment at the top of that file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..feeds import parse
from ..models import Candidate, Provenance

SOURCE_ID = "fixture"
SOURCE_NAME = "Gazette (synthetic fixture)"

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gazette_synthetic.xml"


def collect() -> list[Candidate]:
    retrieved = datetime.now(timezone.utc)
    items = parse(FIXTURE.read_bytes())
    return [
        Candidate(
            source_id=SOURCE_ID,
            source_name=SOURCE_NAME,
            external_id=i.item_id,
            title=i.title,
            body=i.summary,
            url=i.link,
            published=i.published,
            retrieved=retrieved,
            provenance=Provenance.LIVE,
            raw={"categories": i.categories},
        )
        for i in items
    ]
