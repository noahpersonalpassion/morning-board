"""Turn panel results into the page.

Plain string building, no template engine, no dependencies. The CSS and the
shell live in templates/page.html with four markers; everything else is
generated here.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .panels.base import PanelResult, State
from .whatsnew import SCRIPT as WHATSNEW_SCRIPT, STYLE as WHATSNEW_STYLE, state_blob

TEMPLATE = Path(__file__).resolve().parent / "templates" / "page.html"


def _esc(text: str) -> str:
    """Escape for HTML.

    Panels emit real characters — a degree sign is "\u00b0", not "&deg;" — so
    escaping happens here and only here. The earlier version let panels emit
    entities and tried to preserve them, which put "12.0&deg;C" into
    board.json, where it is not markup but a string with junk in it.
    """
    return html.escape(text, quote=False)


def _row(label: str, r: PanelResult) -> str:
    flag = ""
    if r.flag:
        flag = (f'<span class="flag {r.flag_kind}">{_esc(r.flag)}</span>')

    unit = f' <span class="unit">{_esc(r.unit)}</span>' if r.unit else ""

    link = ""
    if r.link_url and r.link_label:
        link = (f' <a href="{html.escape(r.link_url, quote=True)}" '
                f'target="_blank" rel="noopener">{_esc(r.link_label)}</a>')

    note = (f'<div class="note">{_esc(r.note)}{link}</div>'
            if r.note or link else "")

    return (
        f'<li class="row" data-state="{r.state.value}" data-label="{html.escape(label, quote=True)}">'
        f'<span class="mark" aria-hidden="true"></span>'
        f'<div class="label">{_esc(label)}</div>'
        f'<div class="read">{r.reading}{unit}{flag}</div>'
        f'{r.extra_html}{note}</li>'
    )


def _country(r: PanelResult) -> str:
    if r.state is not State.LIVE:
        return (
            '<ol class="country"><li class="story">'
            '<span class="n">--</span>'
            f'<p>{_esc(r.note or "Could not be read this morning.")}</p>'
            '</li></ol>'
        )
    stories = r.meta.get("stories", [])
    out = []
    for i, s in enumerate(stories, 1):
        where = (f'<span class="where">{_esc(s["where"])}</span>'
                 if s.get("where") else "")
        out.append(
            f'<li class="story"><span class="n">{i:02d}</span>'
            f'<p>{_esc(s["title"])}{where}</p></li>'
        )
    return f'<ol class="country">{"".join(out)}</ol>'


def _off_summary(off: list[tuple[str, PanelResult]]) -> str:
    """Every unbuilt row folded into one line.

    Three full rows reading "Not connected" was a third of the page saying
    nothing, and it made a working board look like a prototype. Collapsing
    them keeps the honesty — they are still listed, still named, still say
    what each one needs — while giving the page back to the rows that have
    something to report. Hiding them entirely would have been the dishonest
    fix: an absent row and a row with nothing to say look identical.
    """
    if not off:
        return ""
    names = ", ".join(label for label, _ in off)
    needs = "; ".join(
        f"{label} {_first_clause(r.note)}" for label, r in off if r.note
    )
    return (
        '<li class="row" data-state="off">'
        '<span class="mark" aria-hidden="true"></span>'
        '<div class="label">Not yet</div>'
        f'<div class="read">{len(off)} <span class="unit">'
        f'{"row" if len(off) == 1 else "rows"}</span></div>'
        f'<div class="note">{_esc(names)}. {_esc(needs)}.</div>'
        '</li>'
    )


def _first_clause(note: str) -> str:
    """"Needs a Gazette API key. Request one from..." -> "needs a Gazette API key"."""
    first = note.split(".")[0].strip()
    return first[0].lower() + first[1:] if first else ""


def render_page(
    *,
    site_name: str,
    place: str,
    rows: list[tuple[str, PanelResult]],
    country: PanelResult,
    tz: str = "Pacific/Auckland",
    pwa_head: str = "",
    pwa_register: str = "",
) -> str:
    now = datetime.now(ZoneInfo(tz))

    on = [(l, r) for l, r in rows if r.state is not State.OFF]
    off = [(l, r) for l, r in rows if r.state is State.OFF]
    board = "".join(_row(label, r) for label, r in on) + _off_summary(off)

    needs = [r for _, r in rows if r.needs_you]
    unread = [r for _, r in rows if r.state in (State.UNREAD, State.PAUSED)]

    # The lede states the day in the reader's terms, and never overclaims:
    # it counts only what was actually read.
    bits = []
    weather = next((r for lbl, r in rows if lbl == "Weather"), None)
    if weather and weather.state is State.LIVE:
        bits.append(weather.note.split(".")[0].rstrip("."))
    if needs:
        n = len(needs)
        bits.append(f"<strong>{n} deadline{'s' if n > 1 else ''} open</strong>")
    near = next((r for lbl, r in rows if lbl == "Near you"), None)
    if near and near.state is State.QUIET:
        bits.append("nothing has changed near your address")
    lede = ". ".join(b[0].upper() + b[1:] for b in bits if b) + "." if bits else ""

    checked = len(on)
    foot_line = (
        f"{len(needs)} thing{'s' if len(needs) != 1 else ''} needs you."
        if needs else "Nothing needs you today."
    )
    if unread:
        foot_line += f" {len(unread)} source{'s' if len(unread) > 1 else ''} could not be read."

    shell = TEMPLATE.read_text(encoding="utf-8")
    cap = country.meta.get("cap", 5)
    source = country.meta.get("source", "")

    return (
        shell
        .replace("<!--TITLE-->", _esc(site_name))
        .replace("<!--STAMP-->", f"{_esc(place)} &middot; "
                                 f"{now.strftime('%a %-d %b')}")
        .replace("<!--LEDE-->", lede)
        .replace("<!--CHECKED-->", f"{checked} checked")
        .replace("<!--PANELS-->", board)
        .replace("<!--COUNTRYCAP-->", f"{cap} &middot; hard cap")
        .replace("<!--COUNTRY-->", _country(country))
        .replace("<!--COUNTRYSOURCE-->", _esc(source) or "unavailable")
        .replace("<!--FOOT-->", _esc(foot_line))
        .replace("<!--BUILT-->", now.strftime("%-d %b %H:%M"))
        .replace("<!--PWAHEAD-->", pwa_head)
        .replace("<!--PWAREG-->", pwa_register)
        .replace("<!--WHATSNEWSTYLE-->", WHATSNEW_STYLE)
        .replace("<!--BOARDSTATE-->", state_blob(on))
        .replace("<!--WHATSNEW-->", WHATSNEW_SCRIPT)
    )


def render_json(rows: list[tuple[str, PanelResult]],
                country: PanelResult) -> str:
    """The same build as data, so the board is readable by other things.

    Publishing this alongside the page costs nothing and means a phone
    widget, a shell script or a friend's own page can read the board without
    scraping it.
    """
    def one(label, r):
        return {
            "label": label, "state": r.state.value, "reading": r.reading,
            "unit": r.unit, "note": r.note, "flag": r.flag,
            "as_of": r.as_of, "meta": r.meta,
        }
    return json.dumps(
        {
            "built": datetime.now(ZoneInfo("Pacific/Auckland")).isoformat(),
            "panels": [one(l, r) for l, r in rows],
            "country": one("The country", country),
        },
        indent=1, ensure_ascii=False,
    )
