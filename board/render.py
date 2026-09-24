"""Turn panel results into the page.

Plain string building, no template engine, no dependencies. The CSS and the
shell live in templates/page.html with markers; everything else is generated
here.

The board is laid out in compartments rather than as one list, and which
compartment a panel gets is decided by `PanelResult.shape` — from its state,
never from the layout's convenience. Size is a claim: a grid of equal boxes
asserts that its contents matter equally, which stops being true the moment
one of them is a deadline you can permanently miss and another is a row with
nothing to report. So:

  CARD    full width, its own colour. Something you can still act on and
          can permanently lose. Never more than a handful, usually none.
  METRIC  a tile in the grid, with an icon, a reading and its own range.
          Things that were measured this morning.
  STRIP   one line. Things with nothing to report, and things not built.
          Present, nameable, and taking almost none of the page.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .glyphs import icon as glyph
from .panels.base import PanelResult, Scale, State
from .freshness import MARKUP as STALE_MARKUP, STYLE as STALE_STYLE, script as stale_script
from .whatsnew import SCRIPT as WHATSNEW_SCRIPT, STYLE as WHATSNEW_STYLE, state_blob

TEMPLATE = Path(__file__).resolve().parent / "templates" / "page.html"


def _esc(text: str) -> str:
    """Escape for HTML.

    Panels emit real characters — a degree sign is "°", not "&deg;" — so
    escaping happens here and only here. The earlier version let panels emit
    entities and tried to preserve them, which put "12.0&deg;C" into
    board.json, where it is not markup but a string with junk in it.
    """
    return html.escape(text, quote=False)


def _link(r: PanelResult) -> str:
    if not (r.link_url and r.link_label):
        return ""
    return (f'<a class="act" href="{html.escape(r.link_url, quote=True)}" '
            f'target="_blank" rel="noopener">{_esc(r.link_label)}</a>')


def _flag(r: PanelResult) -> str:
    if not r.flag:
        return ""
    return f'<span class="flag {r.flag_kind}">{_esc(r.flag)}</span>'


def _bar(s: Scale | None) -> str:
    """The reading's own range, or nothing.

    No bar rather than an empty one when a panel has no meaningful range:
    a flat track reads as zero, which is a measurement the board did not
    take.
    """
    if s is None:
        return ""
    ends = ""
    if s.low_label or s.high_label or s.mid_label:
        ends = (
            '<div class="ends">'
            f'<span>{_esc(s.low_label)}</span>'
            f'<span class="mid">{_esc(s.mid_label)}</span>'
            f'<span>{_esc(s.high_label)}</span>'
            '</div>'
        )
    return (
        f'<div class="bar" role="img" aria-label="{s.pct:.0f} percent of range">'
        f'<i class="fill {s.tone}" style="width:{s.pct:.1f}%"></i></div>{ends}'
    )


def _head(label: str, r: PanelResult, tone: str = "") -> str:
    cls = f' class="{tone}"' if tone else ""
    return (
        f'<div class="ico"{cls}>{glyph(r.icon)}</div>'
        f'<div class="lbl"{cls}>{_esc(label)}</div>'
    )


def _card(label: str, r: PanelResult) -> str:
    """Full width, its own colour: something you can still act on."""
    return (
        f'<section class="card" data-label="{html.escape(label, quote=True)}">'
        f'<div class="card-top">{_head(label, r, "alert")}'
        f'<div class="card-read">{_esc(r.reading)} '
        f'<span class="unit">{_esc(r.unit)}</span></div></div>'
        f'<p class="card-eff">{_esc(r.effect or r.note)}</p>'
        f'{_link(r)}</section>'
    )


def _metric(label: str, r: PanelResult) -> str:
    """A tile: icon, label, reading, its range, and what it means."""
    return (
        f'<li class="tile" data-label="{html.escape(label, quote=True)}">'
        f'<div class="tile-top">{_head(label, r)}</div>'
        f'<div class="read">{_esc(r.reading)}'
        f'<span class="unit">{_esc(r.unit)}</span>{_flag(r)}</div>'
        f'{_bar(r.scale)}'
        f'<p class="eff">{_esc(r.effect)}</p>'
        f'{_link(r)}</li>'
    )


def _wide(label: str, r: PanelResult) -> str:
    """A panel's own drawing, given the full width under the grid.

    The week chart does not belong inside a half-width tile — seven bars in
    170px is a smear. Pulling it out keeps the 2×2 grid square, which is
    what makes the values scannable, and gives the chart room to be read.
    """
    if not r.extra_html:
        return ""
    return (f'<li class="tile wide" data-label="{html.escape(label + " week", quote=True)}">'
            f'<div class="tile-top">{_head("The week", r)}</div>'
            f'{r.extra_html}</li>')


def _strip(label: str, r: PanelResult) -> str:
    """One line for anything with nothing to report."""
    return (
        f'<li class="strip" data-state="{r.state.value}" '
        f'data-label="{html.escape(label, quote=True)}">'
        f'{_head(label, r)}'
        f'<p class="strip-note">{_esc(r.effect or r.note)}</p>'
        f'<span class="strip-read">{_esc(r.reading)}</span></li>'
    )


def _alert(r: PanelResult | None) -> str:
    """The bar, rendered only when something crossed a line.

    An empty alert bar is worse than no alert bar: it is permanent
    furniture in the place alerts appear, which is how a reader learns to
    skip that place. A quiet day produces no markup at all.
    """
    if r is None or r.state is not State.URGENT:
        return ""
    return (
        '<aside class="alert" role="alert">'
        f'<div class="alert-top"><div class="ico alert-ico">{glyph("alert")}</div>'
        f'<span class="alert-tag">{_esc(r.flag or "alert")}</span>'
        f'<span class="alert-read">{_esc(r.reading)}</span></div>'
        f'<p class="alert-eff">{_esc(r.effect)}</p>'
        f'<p class="alert-note">{_esc(r.note)}{_link(r)}</p>'
        '</aside>'
    )


def _country(r: PanelResult) -> str:
    if r.state is not State.LIVE:
        return (f'<p class="country-empty">'
                f'{_esc(r.note or "Could not be read this morning.")}</p>')
    out = []
    for s in r.meta.get("stories", []):
        where = (f'<span class="where">{_esc(s["where"])}</span>'
                 if s.get("where") else "")
        n = int(s.get("outlets") or 0)
        who = ", ".join(s.get("outlet_names") or [])
        seen = (f'<span class="seen" title="{html.escape(who, quote=True)}">'
                f'{n}</span>') if n else ""
        out.append(f'<li class="story">{seen}'
                   f'<p>{_esc(s["title"])}{where}</p></li>')
    return f'<ol class="country">{"".join(out)}</ol>'


def _off_summary(off: list[tuple[str, PanelResult]]) -> str:
    """Every unbuilt row folded into one strip.

    Still listed, still named, still says what each needs — but given the
    space a thing with nothing to report deserves. Hiding them entirely
    would be the dishonest fix: an absent row and a row with nothing to say
    look identical to a reader, and only one of them is true.
    """
    if not off:
        return ""
    names = ", ".join(label for label, _ in off)
    needs = "; ".join(f"{label} {_first_clause(r.note)}"
                      for label, r in off if r.note)
    return (
        '<li class="strip" data-state="off">'
        f'<div class="ico">{glyph("blank")}</div>'
        '<div class="lbl">Not yet</div>'
        f'<p class="strip-note">{_esc(names)}. {_esc(needs)}.</p>'
        f'<span class="strip-read">{len(off)}</span></li>'
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
    alert: PanelResult | None = None,
    tz: str = "Pacific/Auckland",
    pwa_head: str = "",
    pwa_register: str = "",
) -> str:
    now = datetime.now(ZoneInfo(tz))

    on = [(l, r) for l, r in rows if r.state is not State.OFF]
    off = [(l, r) for l, r in rows if r.state is State.OFF]

    cards = [(l, r) for l, r in on if r.shape == "card"]
    metrics = [(l, r) for l, r in on if r.shape == "metric"]
    strips = [(l, r) for l, r in on if r.shape == "strip"]

    cards_html = "".join(_card(l, r) for l, r in cards)
    grid_html = ("".join(_metric(l, r) for l, r in metrics)
                 + "".join(_wide(l, r) for l, r in metrics))
    grid_html = f'<ul class="grid">{grid_html}</ul>' if metrics else ""
    strips_html = "".join(_strip(l, r) for l, r in strips) + _off_summary(off)
    strips_html = f'<ul class="strips">{strips_html}</ul>' if strips_html else ""

    needs = [r for _, r in rows if r.needs_you]
    unread = [r for _, r in rows if r.state in (State.UNREAD, State.PAUSED)]

    # The lede states the day in the reader's terms and never overclaims:
    # it counts only what was actually read. Deliberately the `effect`, not
    # the `note` — the note's job is provenance, and the day it began
    # "Source: Open-Meteo", so did the lede.
    bits = []
    if alert is not None and alert.state is State.URGENT:
        bits.append(f"<strong>{_esc(alert.reading)} earthquake overnight</strong>"
                    if alert.reading.startswith("M")
                    else f"<strong>{_esc(alert.reading)}</strong>")
    weather = next((r for lbl, r in rows if lbl == "Weather"), None)
    if weather and weather.state is State.LIVE and weather.effect:
        bits.append(weather.effect.split(".")[0].rstrip("."))
    if needs:
        n = len(needs)
        bits.append(f"<strong>{n} deadline{'s' if n > 1 else ''} open</strong>")
    near = next((r for lbl, r in rows if lbl == "Near you"), None)
    if near and near.state is State.QUIET:
        bits.append("nothing has changed near your address")
    lede = ". ".join(b[0].upper() + b[1:] for b in bits if b) + "." if bits else ""

    foot_line = (
        f"{len(needs)} thing{'s' if len(needs) != 1 else ''} needs you."
        if needs else "Nothing needs you today."
    )
    if unread:
        foot_line += (f" {len(unread)} source"
                      f"{'s' if len(unread) > 1 else ''} could not be read.")

    shell = TEMPLATE.read_text(encoding="utf-8")
    return (
        shell
        .replace("<!--TITLE-->", _esc(site_name))
        .replace("<!--STAMP-->", f"{_esc(place)} &middot; "
                                 f"{now.strftime('%a %-d %b')}")
        .replace("<!--LEDE-->", lede)
        .replace("<!--ALERT-->", _alert(alert))
        .replace("<!--CARDS-->", cards_html)
        .replace("<!--GRID-->", grid_html)
        .replace("<!--STRIPS-->", strips_html)
        .replace("<!--CHECKED-->", f"{len(on)} checked")
        .replace("<!--COUNTRYCAP-->",
                 f"{country.meta.get('cap', 5)} &middot; hard cap")
        .replace("<!--COUNTRY-->", _country(country))
        .replace("<!--COUNTRYEFFECT-->", _esc(country.effect))
        .replace("<!--COUNTRYNOTE-->", _esc(country.note))
        .replace("<!--FOOT-->", _esc(foot_line))
        .replace("<!--BUILT-->", now.strftime("%-d %b %H:%M"))
        .replace("<!--PWAHEAD-->", pwa_head)
        .replace("<!--PWAREG-->", pwa_register)
        .replace("<!--WHATSNEWSTYLE-->", WHATSNEW_STYLE)
        .replace("<!--STALESTYLE-->", STALE_STYLE)
        .replace("<!--STALE-->", STALE_MARKUP)
        .replace("<!--STALESCRIPT-->", stale_script(now.isoformat()))
        .replace("<!--BOARDSTATE-->", state_blob(on))
        .replace("<!--WHATSNEW-->", WHATSNEW_SCRIPT)
    )


def render_json(rows: list[tuple[str, PanelResult]],
                country: PanelResult,
                alert: PanelResult | None = None) -> str:
    """The same build as data, so the board is readable by other things.

    Publishing this alongside the page costs nothing and means a phone
    widget, a shell script or a friend's own page can read the board
    without scraping it.
    """
    def one(label, r):
        out = {
            "label": label, "state": r.state.value, "reading": r.reading,
            "unit": r.unit, "effect": r.effect, "note": r.note,
            "flag": r.flag, "shape": r.shape, "as_of": r.as_of,
            "meta": r.meta,
        }
        if r.scale is not None:
            out["scale"] = {
                "value": r.scale.value, "low": r.scale.low,
                "high": r.scale.high, "pct": round(r.scale.pct, 1),
            }
        return out

    return json.dumps(
        {
            "built": datetime.now(ZoneInfo("Pacific/Auckland")).isoformat(),
            "panels": [one(l, r) for l, r in rows],
            "country": one("The country", country),
            # Carried so the next build can tell a changed volcanic alert
            # level from a steady one. The board reads its own last output.
            "alert": one("Alert", alert) if alert is not None else None,
        },
        indent=1, ensure_ascii=False,
    )
