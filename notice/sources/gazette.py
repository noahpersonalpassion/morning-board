"""New Zealand Gazette — the primary source.

The Gazette is the official journal of constitutional record: secondary
legislation, departmental notices, land notices, appointments, commercial
proceedings. Published continuously 9am-5pm on working days, free to read,
and effectively unread outside the legal profession.

ACCESS (checked 23 Sep 2026)
---------------------------
RSS requires an API key. Anonymous access is not permitted, and the site
states queries are restricted to one per day. Request a key from
info@gazette.govt.nz. Setup instructions arrive with the key.

That one-query-per-day limit shapes the design: this adapter is built to
pull ONE broad feed per day and do all narrowing locally, rather than
issuing a query per topic. Do not "fix" that by adding more feed URLs.

Until the key arrives, run with the fixture source so the pipeline is
exercised end to end (`notice run --source fixture`).

The exact feed URL template and field names come with the key. FEED_URL
below is a placeholder: set NOTICE_GAZETTE_FEED_URL once you know the real
one, and correct `_to_candidate` against a real item.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from ..feeds import FeedError, read
from ..models import Candidate, Provenance

SOURCE_ID = "gazette"
SOURCE_NAME = "New Zealand Gazette"

# Set from the instructions that arrive with your API key.
FEED_URL_ENV = "NOTICE_GAZETTE_FEED_URL"
API_KEY_ENV = "NOTICE_GAZETTE_API_KEY"


def _feed_url() -> str:
    url = os.environ.get(FEED_URL_ENV, "").strip()
    if not url:
        raise FeedError(
            "No Gazette feed URL configured. Request a key from "
            "info@gazette.govt.nz, then set "
            f"{FEED_URL_ENV} (and {API_KEY_ENV} if the key is a separate "
            "parameter). Until then run with --source fixture."
        )
    key = os.environ.get(API_KEY_ENV, "").strip()
    if key and "{key}" in url:
        url = url.replace("{key}", key)
    return url


def _to_candidate(item, retrieved: datetime) -> Candidate:
    """Map one feed item to a Candidate.

    Correct this once you have seen a real item: the Gazette may carry the
    notice number, notice type code and issuing agency in `category`, in the
    description, or in a namespaced element this parser currently drops into
    `raw`. Everything downstream reads Candidate, so this is the only place
    that needs to change.
    """
    return Candidate(
        source_id=SOURCE_ID,
        source_name=SOURCE_NAME,
        external_id=item.item_id,
        title=item.title,
        body=item.summary,
        url=item.link,
        published=item.published,
        retrieved=retrieved,
        provenance=Provenance.LIVE,
        raw={"categories": item.categories},
    )


def collect() -> list[Candidate]:
    retrieved = datetime.now(timezone.utc)
    items = read(_feed_url())
    return [_to_candidate(i, retrieved) for i in items]
