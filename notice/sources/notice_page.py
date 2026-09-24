"""Fetch a single notice's own Gazette page, for the region tag.

Why this exists: 34 notices in the six-week corpus name a place the title
does not identify - "Revocation of the Reservation Over a Reserve",
"Land Declared No Longer Needed for Education Purposes". The notice page
carries the answer as a structured tag. A real page reads:

    Notice Type    Land Notices
    Notice Title   Land (Subsurface) ... 42 Upper Queen Street, Auckland Central
    Publication Date  18 SEP 2026
    Tags           Public Works Act | Other Councils | Auckland
    Notice Number  2026-ln5366

That "Auckland" is the region, given rather than inferred, and it is the
cheapest correct answer available.

TWO CONSTRAINTS, both learned the hard way, both deliberate in this design:

1. gazette.govt.nz sits behind Imperva bot protection. Scripted fetches get
   an empty shell while the search results render client-side. This module
   therefore fetches ONE notice at a time, politely, with a real delay, and
   caches every result permanently. It is not a scraper and must not become
   one: at 20 notices a day, a day's worth is 20 requests.

2. It is a fallback, not the main path. The licensed RSS feed is the
   supported way in, and the Gazette limits queries to one per day. Use this
   only to resolve candidates that already passed every other criterion and
   failed solely on location - typically a handful a day.

Nothing here runs from a sandbox that cannot reach gazette.govt.nz. Run it
on a machine that can, and the cache travels with the repo.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..feeds import FeedError, fetch

CACHE = Path(__file__).resolve().parents[2] / "out" / "notice_pages.json"
POLITE_DELAY_SECONDS = 2.0

# The page renders labelled blocks. Tags sit between the Tags label and the
# Notice Number label; each tag is its own element, so they arrive newline
# separated once markup is stripped.
TAGS_RE = re.compile(
    r"Tags\s*(.*?)\s*Notice Number", re.S | re.I
)
TAG_SPLIT_RE = re.compile(r"\s*[\n|]\s*")
TAG_STRIP_RE = re.compile(r"<[^>]+>")


@dataclass
class NoticePage:
    number: str
    tags: list[str]
    body: str


def parse(html: str) -> NoticePage | None:
    """Pull the tags and body out of a notice page.

    Returns None rather than guessing when the Tags block is absent - which
    is what a bot-protection shell looks like, and treating a shell as "no
    tags" would silently mark every notice unlocatable.
    """
    text = TAG_STRIP_RE.sub("\n", html)
    m = TAGS_RE.search(text)
    if not m:
        return None
    tags = [t.strip() for t in TAG_SPLIT_RE.split(m.group(1)) if t.strip()]
    num = re.search(r"\b(20\d\d-[a-z]{2}\d+)\b", text, re.I)
    return NoticePage(
        number=num.group(1) if num else "",
        tags=tags,
        body="",
    )


class PageCache:
    """Permanent cache. A gazetted notice never changes after publication,
    so a page fetched once never needs fetching again."""

    def __init__(self, path: Path = CACHE) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, list[str]] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, number: str) -> list[str] | None:
        return self._data.get(number)

    def put(self, number: str, tags: list[str]) -> None:
        self._data[number] = tags
        self.path.write_text(
            json.dumps(self._data, indent=1, ensure_ascii=False),
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._data)


def resolve(number: str, cache: PageCache | None = None) -> list[str] | None:
    """Region tags for one notice. Cached forever; polite when it is not."""
    cache = cache or PageCache()
    hit = cache.get(number)
    if hit is not None:
        return hit
    url = f"https://gazette.govt.nz/notice/id/{number}"
    try:
        html = fetch(url, timeout=30).decode("utf-8", "replace")
    except FeedError:
        return None
    page = parse(html)
    if page is None:
        return None
    cache.put(number, page.tags)
    time.sleep(POLITE_DELAY_SECONDS)
    return page.tags


def resolve_many(numbers: list[str], limit: int = 25) -> dict[str, list[str]]:
    """Resolve a day's unresolved candidates.

    `limit` is a hard stop, not a suggestion. If a run wants more than 25
    pages, the filter upstream is too loose - fix that rather than raising
    this.
    """
    cache = PageCache()
    out: dict[str, list[str]] = {}
    for n in numbers[:limit]:
        tags = resolve(n, cache)
        if tags:
            out[n] = tags
    return out
