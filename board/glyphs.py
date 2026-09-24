"""The tile glyphs, as inline stroke SVG.

Not to be confused with `board/icons.py`, which draws the PNG home-screen
icon at build time. That one is a picture of the board; these are the small
marks inside it. They were briefly the same filename, and the collision
silently replaced the icon generator — hence two clearly different names.

Inline rather than an icon font or a sprite sheet, for the same reason the
rest of the board inlines everything: the page has to render correctly on a
phone in a dead spot, weeks after it was built, with nothing to fetch. An
icon that needs the network is an icon that is sometimes a blank square.

Panels name an icon by key, never by markup — `PanelResult.icon` is a
lookup into this table. A panel that could emit its own SVG could emit
anything, and nothing on this board should be able to put arbitrary markup
on the page.

All are 24×24, stroke-only, and inherit `currentColor`, so a tile's own
colour carries the glyph and there is no palette to keep in sync.
"""

from __future__ import annotations

_P = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
      'aria-hidden="true" focusable="false">')

ICONS: dict[str, str] = {
    "weather": _P + (
        '<path d="M7 16a4.5 4.5 0 01.6-9A6 6 0 0119 9.5a3.5 3.5 0 01-.5 6.5"/>'
        '<path d="M9 19l-1 2M13 19l-1 2M17 19l-1 2"/>'
    ) + "</svg>",
    "sunset": _P + (
        '<path d="M3 18h18"/><path d="M8 14a4 4 0 018 0"/>'
        '<path d="M12 3v3M5 7l2 2M19 7l-2 2"/><path d="M9 21l3-3 3 3"/>'
    ) + "</svg>",
    "sun": _P + (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5'
        'M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>'
    ) + "</svg>",
    "fuel": _P + (
        '<path d="M4 21V5a2 2 0 012-2h5a2 2 0 012 2v16"/><path d="M3 21h11"/>'
        '<path d="M6 8h5"/>'
        '<path d="M16 12h2a1 1 0 011 1v4a1.5 1.5 0 003 0V9l-2.5-2.5"/>'
    ) + "</svg>",
    "air": _P + (
        '<path d="M3 8h11a3 3 0 100-3"/><path d="M3 12h15a3 3 0 113 3"/>'
        '<path d="M3 16h9a2.5 2.5 0 110 5"/>'
    ) + "</svg>",
    "clock": _P + '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    "pin": _P + (
        '<path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z"/>'
        '<circle cx="12" cy="10" r="2.5"/>'
    ) + "</svg>",
    "globe": _P + (
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
        '<path d="M12 3a15 15 0 010 18a15 15 0 010-18z"/>'
    ) + "</svg>",
    "alert": _P + (
        '<path d="M12 3l9 16H3l9-16z"/><path d="M12 9v4"/>'
        '<path d="M12 16.5v.5"/>'
    ) + "</svg>",
    "bus": _P + (
        '<rect x="4" y="4" width="16" height="13" rx="2"/>'
        '<path d="M4 10h16"/><path d="M7 21v-2M17 21v-2"/>'
        '<path d="M8 14v.5M16 14v.5"/>'
    ) + "</svg>",
    "bin": _P + (
        '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2"/>'
        '<path d="M6 7l1 13a1 1 0 001 1h8a1 1 0 001-1l1-13"/>'
    ) + "</svg>",
    "blank": _P + '<circle cx="12" cy="12" r="8"/></svg>',
}


def icon(name: str) -> str:
    """The glyph, or a neutral circle. Never raises and never renders empty.

    A missing icon is a typo in a panel, not a reason for a tile to lose its
    left column and sit misaligned beside its neighbours.
    """
    return ICONS.get(name or "", ICONS["blank"])
