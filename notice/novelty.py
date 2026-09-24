"""Criterion 4: has this already been reported?

This is the criterion that makes Notice un-clonable by a news organisation,
so it is the one worth getting right. It is also the only criterion that
depends on a source that can be offline — and when it is offline, novelty is
UNVERIFIED, not true. The default is to refuse to ship rather than guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .feeds import FeedError, read

# Words that carry no distinguishing signal in NZ civic/news text.
STOPWORDS = frozenset("""
a an and are as at be been but by for from has have how in into is it its
more new not of on or over that the their there they this to under up was
were what when where which who will with your new zealand nz says say said
after before amid could would should may might can also just than then
""".split())

TOKEN_RE = re.compile(r"[a-z0-9$]+")


def significant_terms(text: str) -> set[str]:
    """Distinctive terms only: drops stopwords and very short words, keeps
    numbers and money amounts (they are often the most identifying part)."""
    out: set[str] = set()
    for tok in TOKEN_RE.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        if any(ch.isdigit() for ch in tok) or len(tok) >= 4:
            out.add(tok)
    return out


@dataclass
class Headline:
    title: str
    outlet: str
    published: datetime
    url: str = ""
    terms: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.terms:
            self.terms = significant_terms(self.title)


@dataclass
class Match:
    headline: Headline
    score: float
    shared: list[str]


class HeadlineCorpus:
    """Recent coverage from major NZ outlets.

    `available` is False when no feed could be read. Callers must treat that
    as "novelty unverified", never as "novel".
    """

    def __init__(self, window_days: int = 7) -> None:
        self.window_days = window_days
        self.headlines: list[Headline] = []
        self.outlets_ok: list[str] = []
        self.outlets_failed: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return bool(self.headlines)

    # -- loading ---------------------------------------------------------

    def load_feeds(self, feeds: dict[str, str]) -> None:
        """feeds: {outlet name: rss url}. A dead feed is recorded, not fatal."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        for outlet, url in feeds.items():
            try:
                items = read(url)
            except FeedError as e:
                self.outlets_failed.append((outlet, str(e)))
                continue
            kept = 0
            for i in items:
                if i.published >= cutoff:
                    self.headlines.append(Headline(
                        title=i.title, outlet=outlet,
                        published=i.published, url=i.link,
                    ))
                    kept += 1
            if kept:
                self.outlets_ok.append(outlet)
            else:
                self.outlets_failed.append(
                    (outlet, "no items inside the window")
                )

    def load_fixture(self, path: Path) -> None:
        """Offline corpus: [{"title","outlet","published","url"}, ...]"""
        data = json.loads(Path(path).read_text())
        for row in data:
            published = datetime.fromisoformat(
                row["published"].replace("Z", "+00:00")
            )
            self.headlines.append(Headline(
                title=row["title"],
                outlet=row.get("outlet", "fixture"),
                published=published,
                url=row.get("url", ""),
            ))
        if self.headlines:
            self.outlets_ok.append("fixture")

    # -- querying --------------------------------------------------------

    def best_match(self, text: str, threshold: float = 0.45) -> Match | None:
        """Overlap coefficient over distinctive terms.

        Overlap (not Jaccard) because a headline is much shorter than a
        notice body, and Jaccard would punish that length difference and
        let real coverage through.
        """
        terms = significant_terms(text)
        if not terms:
            return None
        best: Match | None = None
        for h in self.headlines:
            if not h.terms:
                continue
            shared = terms & h.terms
            if len(shared) < 2:      # one shared word is coincidence
                continue
            score = len(shared) / min(len(terms), len(h.terms))
            if score >= threshold and (best is None or score > best.score):
                best = Match(headline=h, score=round(score, 3),
                             shared=sorted(shared))
        return best
