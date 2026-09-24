"""Who the board is for, and which panels it runs.

One file to edit to make the board yours. Nothing here is secret: API keys
come from the environment, never from this file, so it is safe to commit and
safe to fork.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from notice.delta import Profile
from notice.novelty import HeadlineCorpus
from notice.reader import Reader, ReaderConfigError, load as load_reader


@dataclass
class Site:
    name: str
    place: str
    lat: float
    lon: float
    timezone: str = "Pacific/Auckland"
    out_dir: Path = Path("site")


def _reader() -> Reader:
    """Everything about the reader comes from reader.json.

    One file to edit, validated on load, with errors that name the fix. The
    board is meant to be forked, so a stranger's first build must fail with a
    sentence rather than a stack trace.
    """
    return load_reader(os.environ.get("BOARD_READER_CONFIG"))


def site() -> Site:
    r = _reader()
    return Site(name=r.name, place=r.place, lat=r.lat, lon=r.lon)


def reader() -> Profile:
    """The reader's matching profile. Never leaves the build machine."""
    return _reader().profile


def headline_corpus() -> HeadlineCorpus:
    """Criterion 4's corpus, shared by Near You and The country.

    Both halves of the board read the same news. One uses it to stay silent,
    the other to summarise — which is the point.
    """
    from board.news import NEWS_FEEDS
    corpus = HeadlineCorpus(window_days=7)
    corpus.load_feeds(NEWS_FEEDS)
    if not corpus.available:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "headlines_synthetic.json"
        if fixture.exists() and os.environ.get("BOARD_ALLOW_FIXTURE_CORPUS"):
            corpus.load_fixture(fixture)
    return corpus


def gazette_key() -> str:
    return os.environ.get("NOTICE_GAZETTE_API_KEY", "")


def legislation_key() -> str:
    return os.environ.get("NOTICE_LEGISLATION_API_KEY", "")
