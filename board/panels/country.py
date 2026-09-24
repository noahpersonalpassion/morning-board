"""The country: what everyone is talking about, hard-capped.

Two rules make this a panel rather than a feed.

ONE: the cap is fixed, not "today's count". On a big news day a feed grows
and eats the morning; this does not. Five is five.

TWO: it never grows during the day. Everything else on the board can gain an
item between reads. This can only lose one. That is the structural property
that stops the board becoming the thing it replaces.

It is also the other half of the Delta Rule. A change everyone is discussing
belongs here; a change nobody reported belongs in Near You. Criterion 4
sorts between the two rather than deleting one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from notice.feeds import FeedError, read
from .base import Panel, PanelResult, State

CAP = 5

# Regional tags, so a reader can see at a glance whether a story is near them.
REGION_HINTS = {
    "Auckland": ["auckland", "manukau", "waitakere", "north shore", "papakura"],
    "Wellington": ["wellington", "hutt", "porirua", "kapiti"],
    "Christchurch": ["christchurch", "canterbury", "Ōtautahi"],
    "Dunedin": ["dunedin", "otago"],
    "Waikato": ["waikato", "hamilton", "tauranga"],
}

TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class CountryPanel:
    feed_url: str = "https://www.rnz.co.nz/rss/national.xml"
    source_name: str = "RNZ"
    cap: int = CAP
    panel_id: str = "country"
    label: str = "The country"

    def render(self) -> PanelResult:
        items = read(self.feed_url, timeout=25)
        if not items:
            raise FeedError(f"{self.source_name} returned no items")

        stories = []
        for item in items[: self.cap]:
            title = TAG_RE.sub("", item.title).strip()
            stories.append({"title": title, "where": _where(title + " " + item.summary)})

        return PanelResult(
            state=State.LIVE,
            reading=str(len(stories)),
            unit="of many",
            meta={"stories": stories, "source": self.source_name,
                  "cap": self.cap},
        )


def _where(text: str) -> str:
    low = text.lower()
    for region, terms in REGION_HINTS.items():
        if any(t in low for t in terms):
            return region
    return ""
