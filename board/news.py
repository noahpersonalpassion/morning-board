"""The news feeds, in one place.

Used twice, for opposite purposes: The country panel counts how many of
these independently carried each story, and criterion 4 uses the same
headlines to decide what Near You must stay silent about.

An outlet may list several feeds. They collapse under one outlet name on
purpose — the number that ends up on the page is *independent newsrooms*,
and four RNZ topic feeds carrying one story is one newsroom carrying it.
Listing more feeds per outlet buys coverage, never corroboration.

Two absences worth recording, so nobody wastes an afternoon re-adding them:

  NZ HERALD is not here because its robots.txt disallows the feed. It is
  probably the most-read newsroom in the country and its absence genuinely
  weakens the count below — but a board built on "read the primary source
  and show your working" does not get to ignore a publisher who said no.

  1NEWS is not here because it no longer publishes a feed at any path this
  found. If that changes it belongs back in immediately.

That leaves four newsrooms, which is a real ceiling on how high any
corroboration count on this board can go. It is a fact about the size of
New Zealand's media market, not a bug, and the panel states its own
denominator on the page so the ceiling is visible rather than implied.
"""

from __future__ import annotations

NEWS_FEEDS: dict[str, str | list[str]] = {
    # Public broadcaster, no paywall, the widest topic coverage available.
    "RNZ": [
        "https://www.rnz.co.nz/rss/national.xml",
        "https://www.rnz.co.nz/rss/political.xml",
        "https://www.rnz.co.nz/rss/business.xml",
        "https://www.rnz.co.nz/rss/health.xml",
        "https://www.rnz.co.nz/rss/regional.xml",
        "https://www.rnz.co.nz/rss/te-manu-korihi.xml",
        "https://www.rnz.co.nz/rss/ldr.xml",
    ],
    "Stuff": "https://www.stuff.co.nz/rss",
    # Both of these run to analysis rather than breaking news, so they
    # corroborate less often than their size suggests. Kept because when
    # they do carry a story it is usually one that matters.
    "The Spinoff": "https://thespinoff.co.nz/feed",
    "Newsroom": "https://newsroom.co.nz/feed/",
}
