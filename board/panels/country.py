"""The country: what the most newsrooms independently reported, hard-capped.

Every other panel on this board reads an instrument. Open-Meteo does not
have an opinion about the weather, MBIE does not spin the price of petrol,
and GeoNet does not frame an earthquake. This panel is the one place the
board takes information from people who write for a living, and it is
therefore the one place a frame can get in.

The old version made that worse than it needed to be: it took the first five
items from RNZ's national feed, which is RNZ's running order. One newsroom's
duty editor was choosing what appeared on your board.

So this panel no longer asks an outlet what matters. It asks **how many
outlets independently reported the same thing** — which is a count, not a
judgement, and is the one property of a news story that survives the way it
is written up. Six newsrooms carrying a story is evidence the event happened
and is consequential. It is not evidence anyone framed it well, and this
panel does not claim otherwise.

Three consequences of that design, all deliberate:

  1. **The headline shown is the shortest one in the cluster.** Length in a
     headline is almost entirely editorial addition — the adjectives, the
     angle, the outrage. The shortest rendering of a story is the closest
     any of these outlets got to just saying what happened.

  2. **The corroboration count is displayed.** "4 outlets" is a fact you can
     check. It lets you weigh a story without trusting this board's ordering.

  3. **When corroboration cannot be measured it says so.** If only one feed
     loaded, the count is meaningless, and the panel reports recency instead
     and states plainly that it is doing so. A degraded measurement announced
     is useful; a degraded measurement presented as the real one is a lie.

The two original rules still hold. The cap is fixed at five, not "today's
count", so a big news day cannot eat your morning. And this is the only part
of the board that can shrink during the day but never grow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from notice.feeds import FeedError, read
from notice.novelty import Headline, HeadlineCorpus
from .base import Panel, PanelResult, State

CAP = 5

# How recent a headline must be to count as "the country today". The corpus
# itself keeps seven days because novelty checking needs the longer memory;
# a morning board does not.
WINDOW_HOURS = 48

# Significant terms two headlines must share before they are treated as the
# same story. Two is too loose ("police" plus "auckland" matches half a
# newsroom's output); four starts splitting real clusters on synonyms.
SAME_STORY_TERMS = 3

# Below this many working feeds, a corroboration count means nothing.
MIN_OUTLETS_FOR_COUNTING = 2

REGION_HINTS = {
    "Auckland": ["auckland", "manukau", "waitakere", "north shore", "papakura"],
    "Wellington": ["wellington", "hutt", "porirua", "kapiti"],
    "Christchurch": ["christchurch", "canterbury", "ōtautahi"],
    "Dunedin": ["dunedin", "otago"],
    "Waikato": ["waikato", "hamilton", "tauranga"],
}

TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Exclusion:
    name: str
    because: str
    terms: tuple[str, ...]


# The one editorial judgement on this panel, made once, in public, in a list
# you can read and change — rather than a hundred times, invisibly, in a
# ranking function.
#
# The board's subject is changes to your circumstances. A sports result is a
# real event that changes nobody's: no deadline moves, no price changes, no
# entitlement appears or lapses. Left in, these crowd out the four or five
# slots that exist precisely to stop the panel growing.
#
# The cost is real and worth stating. "Rugby World Cup bid costs ratepayers
# $50m" is a civic story wearing sport's vocabulary, and this drops it. That
# is why the count of what was set aside is printed on the page: a reader who
# thinks the rule is wrong can see it firing rather than wonder what is
# missing.
SET_ASIDE = (
    Exclusion(
        "sport", "a result changes nobody's circumstances",
        ("rugby", "cricket", "netball", "football", "soccer", "basketball",
         "golf", "tennis", "olympic", "commonwealth games", "america's cup",
         "all blacks", "black caps", "blackcaps", "silver ferns", "warriors",
         "phoenix", "super rugby", "nrl", "test match", "world cup",
         "grand final", "formula one", "sailing", "regatta", "marathon",
         "athletics", "boxing", "cycling", "sailor", "halfback", "striker"),
    ),
    Exclusion(
        "entertainment", "a release is not a change to your week",
        ("netflix", "box office", "reality tv", "celebrity", "red carpet",
         "oscars", "grammys", "eurovision", "new album", "season finale"),
    ),
)


def set_aside(title: str) -> str:
    """Which declared exclusion, if any, this headline falls under."""
    low = title.lower()
    for ex in SET_ASIDE:
        if any(t in low for t in ex.terms):
            return ex.name
    return ""


@dataclass
class Cluster:
    """One event, as reported by one or more newsrooms.

    `terms` is the *seed* headline's significant words and never changes.
    Both obvious alternatives are worse: growing it by union lets a cluster
    accumulate vocabulary until it swallows unrelated stories, and shrinking
    it by intersection makes each join harder than the last, so clusters
    stall at two members and the ranking collapses back into recency. A
    fixed seed keeps the rule stable and explainable — everything in here
    shares at least three significant words with the first headline seen.
    """

    headlines: list[Headline] = field(default_factory=list)
    terms: set[str] = field(default_factory=set)

    @property
    def outlets(self) -> list[str]:
        return sorted({h.outlet for h in self.headlines})

    @property
    def newest(self) -> datetime:
        return max(h.published for h in self.headlines)

    @property
    def plainest(self) -> Headline:
        """The shortest headline: the least editorialised rendering here.

        Ties break on the oldest, which is the outlet that got there first
        rather than the one that rewrote it best.
        """
        return sorted(self.headlines, key=lambda h: (len(h.title), h.published))[0]


def cluster_headlines(headlines: list[Headline]) -> list[Cluster]:
    """Group headlines describing the same event.

    Deliberately simple and deterministic: shared significant terms, greedy
    assignment, no model. A reader who wants to know why two stories merged
    can compare the words in them, which is not true of anything smarter.
    """
    clusters: list[Cluster] = []
    for h in sorted(headlines, key=lambda x: x.published, reverse=True):
        if len(h.terms) < SAME_STORY_TERMS:
            continue
        for c in clusters:
            if len(c.terms & h.terms) >= SAME_STORY_TERMS:
                c.headlines.append(h)
                break
        else:
            clusters.append(Cluster(headlines=[h], terms=set(h.terms)))
    return clusters


@dataclass
class CountryPanel:
    corpus: HeadlineCorpus | None = None
    feed_url: str = "https://www.rnz.co.nz/rss/national.xml"
    source_name: str = "RNZ"
    cap: int = CAP
    panel_id: str = "country"
    label: str = "The country"

    def render(self) -> PanelResult:
        if self.corpus is not None and len(self.corpus.outlets_ok) >= MIN_OUTLETS_FOR_COUNTING:
            return self._by_corroboration(self.corpus)
        return self._by_recency()

    # -- the real path ---------------------------------------------------

    def _by_corroboration(self, corpus: HeadlineCorpus) -> PanelResult:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
        recent = [h for h in corpus.headlines if h.published >= cutoff]

        kept = [h for h in recent if not set_aside(h.title)]
        dropped = len(recent) - len(kept)
        clusters = cluster_headlines(kept)

        # Most independently reported first; a tie goes to the newer story.
        clusters.sort(key=lambda c: (len(c.outlets), c.newest), reverse=True)
        top = clusters[: self.cap]

        if not top:
            return PanelResult(
                state=State.QUIET,
                reading="Nothing",
                effect="No story in the last two days was carried by enough "
                       "outlets to measure.",
                note=f"Read {len(recent)} headlines from "
                     f"{len(corpus.outlets_ok)} outlets.",
                meta={"stories": [], "source": ", ".join(corpus.outlets_ok),
                      "cap": self.cap, "method": "corroboration"},
            )

        stories = []
        for c in top:
            h = c.plainest
            stories.append({
                "title": TAG_RE.sub("", h.title).strip(),
                "where": _where(h.title),
                "outlets": len(c.outlets),
                "outlet_names": c.outlets,
                "url": h.url,
            })

        best = stories[0]["outlets"]
        return PanelResult(
            state=State.LIVE,
            reading=str(len(stories)),
            unit="of many",
            effect=(
                f"Ranked by how many newsrooms reported each one, not by any "
                f"one outlet's running order. The top story is carried by "
                f"{best} of {len(corpus.outlets_ok)}."
            ),
            note=(
                f"Read {len(recent)} headlines from "
                f"{', '.join(corpus.outlets_ok)} over the last "
                f"{WINDOW_HOURS} hours"
                + (f", setting aside {dropped} sport and entertainment"
                   if dropped else "")
                + ". The shortest version of each headline is shown, because "
                  "length in a headline is mostly angle."
            ),
            meta={"stories": stories, "source": ", ".join(corpus.outlets_ok),
                  "cap": self.cap, "method": "corroboration",
                  "headlines_read": len(recent), "set_aside": dropped},
        )

    # -- the honest fallback ---------------------------------------------

    def _by_recency(self) -> PanelResult:
        """One feed, stated as one feed.

        This is the old behaviour, kept for when the corpus is unavailable —
        but it now says what it is, so a reader is never shown one newsroom's
        running order while being told it is the country's.
        """
        items = read(self.feed_url, timeout=25)
        if not items:
            raise FeedError(f"{self.source_name} returned no items")

        stories = [
            {"title": TAG_RE.sub("", i.title).strip(),
             "where": _where(i.title + " " + i.summary),
             "outlets": 1, "outlet_names": [self.source_name], "url": i.link}
            for i in items[: self.cap]
        ]
        return PanelResult(
            state=State.LIVE,
            reading=str(len(stories)),
            unit="of many",
            effect=(
                f"This is {self.source_name}'s running order, not a "
                f"cross-checked one."
            ),
            flag="one source",
            flag_kind="warn",
            note=(
                "Too few news feeds could be read to count how many outlets "
                "carried each story, so these are simply the most recent from "
                f"{self.source_name}. Ordering here reflects one newsroom's "
                "judgement."
            ),
            meta={"stories": stories, "source": self.source_name,
                  "cap": self.cap, "method": "recency"},
        )


def _where(text: str) -> str:
    low = text.lower()
    for region, terms in REGION_HINTS.items():
        if any(t in low for t in terms):
            return region
    return ""
