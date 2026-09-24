"""The home-screen icon, drawn at build time with no dependencies.

Generating it keeps binary assets out of the repo — there is nothing here
you cannot diff — and means changing the palette changes the icon. It uses
the project's own tiny PNG writer rather than Pillow, so a fork gets an icon
without installing anything.

The mark is the board's own left margin: four rows in four states, each with
a reading of a different length. It looks like the thing it opens.
"""

from __future__ import annotations

from pathlib import Path

from .png import Canvas

# The board's LIGHT palette, deliberately. A home-screen icon does not
# follow the system theme, so it has to work on both wallpapers.
GROUND = (239, 242, 240)
INK = (18, 23, 20)
ACCENT = (20, 86, 75)
ALERT = (163, 42, 28)
WARN = (138, 90, 0)
OFF = (186, 199, 194)

SIZES = (180, 192, 512)

# live, urgent, quiet (outline only), paused — and how long each reading is.
ROWS = (
    (ACCENT, 0.95),
    (ALERT, 0.55),
    (None, 0.75),
    (WARN, 0.40),
)


def draw(size: int) -> Canvas:
    c = Canvas(size, size, GROUND)

    pad = size * 0.22
    gap = (size - 2 * pad) / len(ROWS)
    mark = size * 0.10
    radius = size * 0.022
    line_x0 = pad + mark * 1.9
    line_x1 = size - pad
    line_h = size * 0.034

    for i, (colour, length) in enumerate(ROWS):
        cy = pad + gap * i + gap / 2
        box = (pad, cy - mark / 2, pad + mark, cy + mark / 2)

        if colour is None:
            c.rounded_rect(*box, radius=radius, outline=OFF,
                           width=max(2.0, size * 0.016))
        else:
            c.rounded_rect(*box, radius=radius, fill=colour)

        c.rounded_rect(
            line_x0, cy - line_h / 2,
            line_x0 + (line_x1 - line_x0) * length, cy + line_h / 2,
            radius=line_h / 2,
            fill=INK if i == 0 else OFF,
        )
    return c


def write_icons(out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for size in SIZES:
        name = f"icon-{size}.png"
        (out_dir / name).write_bytes(draw(size).to_png())
        written.append(name)
    return written
