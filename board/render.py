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
from datetime import datetime, timedelta, timezone
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
        # The bare number needs saying out loud. As a `title` alone it was
        # invisible to a screen reader and unreachable on a touch screen,
        # which is most of this board's readers — so the count that is the
        # whole point of this panel was the one thing you could not get at.
        seen = (f'<span class="seen" title="{html.escape(who, quote=True)}">'
                f'{n}<span class="sr"> newsroom{"s" if n != 1 else ""}'
                f'{": " + _esc(who) if who else ""}</span></span>') if n else ""
        # The headline links to the version this board chose — the shortest
        # in its cluster. A story you cannot open is a story you have to
        # take on trust, which is the one thing this panel does not ask for.
        title = _esc(s["title"])
        if s.get("url"):
            title = (f'<a href="{html.escape(s["url"], quote=True)}" '
                     f'target="_blank" rel="noopener">{title}</a>')
        out.append(f'<li class="story">{seen}'
                   f'<p>{title}{where}</p></li>')
    return f'<ol class="country">{"".join(out)}</ol>'


def _method(rows: list[tuple[str, PanelResult]]) -> str:
    """Every row's source and the rule that put it there, in one place.

    The board's claim has always been that it is auditable rather than
    trustworthy, and until now that was true of the code and invisible on
    the page — a reader could not tell a panel that checked and found
    nothing from one that never ran.

    It sits at the foot rather than inside each tile for two reasons. Eight
    disclosure triangles scattered through a 2×2 grid is noise, and the
    interesting question is never "why is the weather here" — it is "why
    is Near You silent" and "why is that the fuel number", which are best
    read together, as a log.

    Rows that reported nothing are listed exactly like rows that did. They
    are the ones a reader is most entitled to be suspicious of.
    """
    items = []
    for label, r in rows:
        parts = [p for p in (r.why, r.note) if p]
        if not parts:
            continue
        items.append(
            f'<div class="m-row"><dt>{_esc(label)}</dt>'
            f'<dd>{_esc(" ".join(parts))}</dd></div>'
        )
    if not items:
        return ""
    return (
        '<details class="method"><summary>Why each of these is here</summary>'
        f'<dl class="m-list">{"".join(items)}</dl>'
        '<p class="m-foot">Every rule above is a number or a test in the '
        'source, not a judgement made this morning. If one of them looks '
        'wrong to you, it is meant to be arguable.</p></details>'
    )


def _off_summary(off: list[tuple[str, PanelResult]]) -> str:
    """Every unbuilt row folded into one strip.

    Still listed, still named, still says what each needs — but given the
    space a thing with nothing to report deserves. Hiding them entirely
    would be the dishonest fix: an absent row and a row with nothing to say
    look identical to a reader, and only one of them is true.
    """
    if not off:
        return ""
    # Each row named once, with what it needs. Listing the names and then
    # repeating them inside the needs gave "Transport. Transport needs the
    # AT feed." — a line that says one thing twice and reads as filler.
    parts = []
    for label, r in off:
        clause = _first_clause(r.note)
        parts.append(f"{label} {clause}" if clause else label)
    return (
        '<li class="strip" data-state="off">'
        f'<div class="ico">{glyph("blank")}</div>'
        '<div class="lbl">Not yet</div>'
        f'<p class="strip-note">{_esc("; ".join(parts))}.</p>'
        f'<span class="strip-read">{len(off)}</span></li>'
    )


def next_reading(now: datetime, tz: str) -> str:
    """When the build next runs, in the reader's own clock.

    The footer used to say "next 06:00" as a literal string, which was true
    only for the half of the year New Zealand is on standard time. GitHub's
    scheduler runs in UTC and does not observe New Zealand daylight saving,
    so the workflow's 18:00 UTC becomes 7am here from the last Sunday in
    September — and a board whose entire argument is "never show a stale
    figure as a current one" would have been quietly wrong about its own
    next reading for six months of every year.

    Converting the real cron time through the reader's zone is correct in
    both halves of the year and needs no maintenance at the switch.
    """
    fires_utc = 18  # the workflow's cron: "0 18 * * *"
    here = now.astimezone(timezone.utc)
    nxt = here.replace(hour=fires_utc, minute=0, second=0, microsecond=0)
    if nxt <= here:
        nxt += timedelta(days=1)
    local = nxt.astimezone(ZoneInfo(tz))
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d}{'am' if local.hour < 12 else 'pm'}"


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

    # The lede answers one question: do I have to do anything? It used to
    # open with the weather, which read well when the board was a list and
    # became pure repetition once the weather got a tile of its own four
    # centimetres below — the same sentence twice inside one glance. So the
    # weather now lives in its tile, and the top line carries what a tile
    # cannot: what needs you, what has not moved, and what went unread.
    bits = []
    if alert is not None and alert.state is State.URGENT:
        bits.append(f"<strong>{_esc(alert.reading)} earthquake overnight</strong>"
                    if alert.reading.startswith("M")
                    else f"<strong>{_esc(alert.reading)}</strong>")
    if needs:
        n = len(needs)
        bits.append(f"<strong>{n} deadline{'s' if n > 1 else ''} open</strong>")
    near = next((r for lbl, r in rows if lbl == "Near you"), None)
    if near and near.state is State.QUIET:
        bits.append("nothing has changed near your address")
    if unread:
        n = len(unread)
        bits.append(f"{n} source{'s' if n > 1 else ''} could not be read")
    if not bits:
        n = len(on)
        bits.append(f"{n} reading{'s' if n != 1 else ''} taken, "
                    f"nothing needs you")
    lede = ". ".join(b[0].upper() + b[1:] for b in bits if b) + "."

    # The end of the board must not congratulate and then contradict. The
    # old footer read "You're caught up." and then, one line below, "1 thing
    # needs you." Both were true in their own way and together they were
    # nonsense: being caught up on the reading is not the same as having
    # nothing left to do, and the page was asserting both at once.
    if needs:
        n = len(needs)
        foot_head = ("One thing still needs you." if n == 1
                     else f"{n} things still need you.")
        foot_line = "Everything else on the board is read."
    elif unread:
        n = len(unread)
        foot_head = "Caught up, with gaps."
        foot_line = (f"{n} source{'s' if n > 1 else ''} could not be read this "
                     f"morning, so {'it is' if n == 1 else 'they are'} shown "
                     f"unread rather than guessed at.")
    else:
        foot_head = "You&rsquo;re caught up."
        foot_line = "Nothing needs you today."

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
        .replace("<!--METHOD-->", _method(rows))
        .replace("<!--CHECKED-->", f"{len(on)} checked")
        .replace("<!--COUNTRYCAP-->",
                 f"{country.meta.get('cap', 5)} at most")
        .replace("<!--COUNTRY-->", _country(country))
        .replace("<!--COUNTRYEFFECT-->", _esc(country.effect))
        .replace("<!--COUNTRYNOTE-->", _esc(country.note))
        .replace("<!--FOOTHEAD-->", foot_head)
        .replace("<!--FOOT-->", _esc(foot_line))
        .replace("<!--NEXT-->", _esc(next_reading(now, tz)))
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
            "country": one("Elsewhere", country),
            # Carried so the next build can tell a changed volcanic alert
            # level from a steady one. The board reads its own last output.
            "alert": one("Alert", alert) if alert is not None else None,
        },
        indent=1, ensure_ascii=False,
    )
