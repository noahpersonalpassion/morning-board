"""The news feeds, in one place.

Used twice, for opposite purposes: The country panel summarises them, and
criterion 4 uses them to decide what Near You must stay silent about.

These URLs change. A dead feed is reported, never fatal — but a corpus of
zero headlines means criterion 4 cannot be verified, and Near You refuses to
ship rather than guess. Check the build log if that row goes quiet forever.
"""

from __future__ import annotations

NEWS_FEEDS = {
    "RNZ": "https://www.rnz.co.nz/rss/national.xml",
    "NZ Herald": "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/nz/",
    "Stuff": "https://www.stuff.co.nz/rss",
    "1News": "https://www.1news.co.nz/feed/",
    "The Spinoff": "https://thespinoff.co.nz/feed",
    "Newsroom": "https://newsroom.co.nz/feed/",
}
