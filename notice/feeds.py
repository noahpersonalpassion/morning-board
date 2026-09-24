"""A small, dependency-free RSS/Atom reader.

Deliberately stdlib-only. A civic tool people are meant to run themselves
should not need a virtualenv to start.
"""

from __future__ import annotations

import gzip
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

USER_AGENT = "notice/0.1 (civic change tracker; contact: you@example.nz)"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class FeedError(RuntimeError):
    """A feed could not be fetched or parsed. Never fatal to a run."""


@dataclass
class FeedItem:
    item_id: str
    title: str
    summary: str
    link: str
    published: datetime
    categories: list[str]


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body
    except urllib.error.HTTPError as e:
        raise FeedError(f"HTTP {e.code} from {url}") from e
    except Exception as e:  # noqa: BLE001 - a dead feed must not kill the run
        raise FeedError(f"{type(e).__name__} fetching {url}: {e}") from e


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _parse_date(raw: str) -> datetime:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)          # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))  # Atom
        except ValueError:
            return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse(xml_bytes: bytes) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom into a common shape."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise FeedError(f"malformed XML: {e}") from e

    items: list[FeedItem] = []

    # RSS 2.0
    for node in root.iterfind(".//item"):
        link = _text(node.find("link"))
        guid = _text(node.find("guid")) or link
        items.append(FeedItem(
            item_id=guid,
            title=_text(node.find("title")),
            summary=_text(node.find("description")),
            link=link,
            published=_parse_date(
                _text(node.find("pubDate")) or _text(node.find("dc:date", _NS))
            ),
            categories=[_text(c) for c in node.iterfind("category") if _text(c)],
        ))

    # Atom
    for node in root.iterfind(".//atom:entry", _NS):
        link_el = node.find("atom:link[@rel='alternate']", _NS)
        if link_el is None:
            link_el = node.find("atom:link", _NS)
        link = link_el.get("href", "") if link_el is not None else ""
        items.append(FeedItem(
            item_id=_text(node.find("atom:id", _NS)) or link,
            title=_text(node.find("atom:title", _NS)),
            summary=(
                _text(node.find("atom:summary", _NS))
                or _text(node.find("atom:content", _NS))
            ),
            link=link,
            published=_parse_date(
                _text(node.find("atom:published", _NS))
                or _text(node.find("atom:updated", _NS))
            ),
            categories=[
                c.get("term", "") for c in node.iterfind("atom:category", _NS)
                if c.get("term")
            ],
        ))

    return items


def read(url: str, timeout: int = 30) -> list[FeedItem]:
    return parse(fetch(url, timeout=timeout))
