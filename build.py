#!/usr/bin/env python3
"""Build the board. Run daily by GitHub Actions; run by hand any time.

    python3 build.py              # writes site/index.html and site/board.json
    python3 build.py --dry-run    # build and print the summary, write nothing

Every panel is attempted. A panel that fails becomes a row saying it could
not be read; it never takes the build down, because a board that fails to
publish teaches the reader nothing, while a board with one honest gap in it
is still worth twenty seconds.

The exit code is 0 whenever a page was written, even with failed panels.
A non-zero exit would fail the Action and leave yesterday's page up — which
is the one outcome worse than an incomplete board.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board import config
from board.news import NEWS_FEEDS
from board.panels.base import State, render_all, safe_render
from board.panels.country import CountryPanel
from board.panels.deadlines import DeadlinesPanel, default_deadlines
from board.panels.fuel import FuelPanel
from board.panels.near_you import NearYouPanel
from board.panels.weather import WeatherPanel
from board.pwa import write_pwa
from board.render import render_json, render_page


def build_panels(site, profile, corpus):
    """Assemble the rows.

    Near You needs a live Gazette feed. Without one it would fall back to the
    six-week archive in fixtures/ and present August's notices as this
    morning's — silent staleness, which is the single failure this board
    exists to refuse. So: no key, no row. It reports itself as OFF and says
    what is missing, which is true and fixable.
    """
    from notice.sources import gazette, harvest

    near: object
    if config.gazette_key() and os.environ.get("NOTICE_GAZETTE_FEED_URL"):
        near = NearYouPanel(profile=profile, collect=gazette.collect,
                            corpus=corpus)
    elif os.environ.get("BOARD_USE_ARCHIVE"):
        # Explicit opt-in, for looking at the design with real material in it.
        near = NearYouPanel(profile=profile, collect=harvest.collect,
                            corpus=corpus)
        near.label = "Near you"
    else:
        near = _OffPanel(
            "near_you", "Near you",
            "Needs a Gazette API key. Request one from info@gazette.govt.nz, "
            "then set NOTICE_GAZETTE_API_KEY and NOTICE_GAZETTE_FEED_URL.",
        )

    return [
        WeatherPanel(lat=site.lat, lon=site.lon),
        DeadlinesPanel(deadlines=default_deadlines()),
        near,
        FuelPanel(),
        _OffPanel("transport", "Transport",
                  "Disruptions on your line. Needs the Auckland Transport feed."),
        _OffPanel("bins", "Bins",
                  "Rubbish and recycling day. Needs your council collection zone."),
    ]


class _OffPanel:
    """A row for something not built or not configured yet.

    Shown rather than omitted, because an absent row and a row with nothing
    to report look identical to a reader, and only one of them is true.
    """

    def __init__(self, panel_id: str, label: str, note: str) -> None:
        self.panel_id, self.label, self._note = panel_id, label, note

    def render(self):
        from board.panels.base import PanelResult, State
        return PanelResult(state=State.OFF, reading="Not connected",
                           note=self._note)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="build")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    site = config.site()
    out_dir = Path(args.out) if args.out else site.out_dir

    print(f"  building {site.name} for {site.place}")

    corpus = config.headline_corpus()
    print(f"  corpus: {len(corpus.headlines)} headlines from "
          f"{len(corpus.outlets_ok)} outlet(s)")
    for outlet, why in corpus.outlets_failed:
        print(f"    ! {outlet}: {why[:90]}")

    panels = build_panels(site, config.reader(), corpus)
    results = render_all(panels)
    country = safe_render(CountryPanel())

    rows = [(p.label, r) for p, r in results]
    for label, r in rows:
        print(f"    [{r.state.value:6}] {label}: {r.reading}")
    print(f"    [{country.state.value:6}] The country: "
          f"{len(country.meta.get('stories', []))} stories")

    data = render_json(rows, country)

    # Icons, manifest and service worker: makes the page installable on a
    # phone home screen and readable offline. Never fatal — a board without
    # an icon is still a board.
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        pwa = write_pwa(out_dir, site.name)
        print(f"  icons: {', '.join(pwa['icons'])}")
    except Exception as exc:  # noqa: BLE001
        print(f"  pwa: skipped ({type(exc).__name__})")
        pwa = {"head": "", "register": "", "icons": []}

    page = render_page(
        site_name=site.name, place=site.place,
        rows=rows, country=country, tz=site.timezone,
        pwa_head=str(pwa["head"]), pwa_register=str(pwa["register"]),
    )

    failed = [l for l, r in rows if r.state in (State.UNREAD, State.PAUSED)]
    if failed:
        print(f"  {len(failed)} panel(s) reported a problem: "
              f"{', '.join(failed)}")

    if args.dry_run:
        print("  dry run: nothing written")
        return 0

    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "board.json").write_text(data, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    print(f"  wrote {out_dir/'index.html'} and {out_dir/'board.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
