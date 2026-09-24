"""notice — run the ingest, apply the Delta Rule, write the decision log.

    python -m notice run --source fixture --corpus fixture
    python -m notice run --source gazette --corpus feeds
    python -m notice summary

During weeks 5-6 there is deliberately no interface beyond this. Read the
log, tune the rules, and find out how many items per week actually exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .delta import build_card, default_profile, evaluate
from .feeds import FeedError
from .log import DecisionLog, summarise
from .models import Decision
from .novelty import HeadlineCorpus
from .sources import fixture as fixture_source
from .sources import gazette as gazette_source
from .sources import harvest as harvest_source
from .sources import real_titles as real_source

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "out" / "decisions.jsonl"
DEFAULT_CARDS = ROOT / "out" / "cards.json"

# Verify these before the first live run — news RSS paths change often.
# A feed that fails is reported, not fatal, but a corpus of zero headlines
# means nothing ships (by design).
NEWS_FEEDS = {
    "RNZ": "https://www.rnz.co.nz/rss/national.xml",
    "NZ Herald": "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/nz/",
    "Stuff": "https://www.stuff.co.nz/rss",
    "1News": "https://www.1news.co.nz/feed/",
    "The Spinoff": "https://thespinoff.co.nz/feed",
    "Newsroom": "https://newsroom.co.nz/feed/",
}


def _build_corpus(kind: str) -> HeadlineCorpus:
    corpus = HeadlineCorpus(window_days=7)
    if kind == "fixture":
        corpus.load_fixture(ROOT / "fixtures" / "headlines_synthetic.json")
    else:
        corpus.load_feeds(NEWS_FEEDS)
    return corpus


def cmd_run(args: argparse.Namespace) -> int:
    log = DecisionLog(Path(args.log))
    profile = default_profile()

    source = {"fixture": fixture_source, "real": real_source,
              "harvest": harvest_source, "gazette": gazette_source}[args.source]
    try:
        candidates = source.collect()
    except FeedError as e:
        print(f"\n  source unavailable: {e}\n", file=sys.stderr)
        return 2

    corpus = _build_corpus(args.corpus)
    print(f"\n  corpus: {len(corpus.headlines)} headlines from "
          f"{len(corpus.outlets_ok)} outlet(s)")
    for outlet, why in corpus.outlets_failed:
        print(f"    ! {outlet}: {why}")

    seen = set() if args.replay else log.seen_keys()
    decisions: list[Decision] = []
    cards = []

    print(f"  {len(candidates)} candidate(s) from {source.SOURCE_NAME}\n")

    for c in candidates:
        if c.key in seen:
            continue
        criteria = evaluate(c, profile, corpus, args.allow_unverified_novelty)
        shipped = all(r.passed for r in criteria)
        card = None
        if shipped:
            try:
                card = build_card(c, criteria, profile.attributes).to_dict()
                cards.append(card)
            except ValueError as e:
                shipped = False
                criteria.append(
                    type(criteria[0])("card", False, str(e))
                )
        decisions.append(Decision(
            key=c.key, run_date=date.today(), source_id=c.source_id,
            title=c.title, url=c.url, shipped=shipped,
            criteria=criteria, card=card,
        ))

        mark = "SHIP" if shipped else "drop"
        print(f"  [{mark}] {c.title[:68]}")
        if not shipped:
            for r in criteria:
                if not r.passed:
                    print(f"         {r.name}: {r.reason}")
                    break

    log.append_all(decisions)
    Path(args.cards).parent.mkdir(parents=True, exist_ok=True)
    Path(args.cards).write_text(
        json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(summarise(log).render())
    print(f"  log:   {args.log}")
    print(f"  cards: {args.cards}\n")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    print(summarise(DecisionLog(Path(args.log))).render())
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="notice")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="ingest, filter, log")
    r.add_argument("--source",
                   choices=["fixture", "real", "harvest", "gazette"],
                   default="real")
    r.add_argument("--corpus", choices=["fixture", "feeds"], default="fixture")
    r.add_argument("--log", default=str(DEFAULT_LOG))
    r.add_argument("--cards", default=str(DEFAULT_CARDS))
    r.add_argument("--replay", action="store_true",
                   help="re-judge candidates already in the log")
    r.add_argument("--allow-unverified-novelty", action="store_true",
                   help="ship when no headline corpus is reachable. Off by "
                        "default: unverified novelty is not novelty.")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("summary", help="read the decision log")
    s.add_argument("--log", default=str(DEFAULT_LOG))
    s.set_defaults(func=cmd_summary)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
