"""A minimal PNG writer, so the icon costs no dependency.

Pillow is not installed on most machines, and adding it would mean the
"nothing to install, nothing to pin, nothing to rot" promise in the README
is false for anyone who wants a home-screen icon. PNG's baseline format is
small enough to write directly: a signature, three chunks, and zlib — all
in the standard library.

Only what the icon needs is implemented: 8-bit RGB, no palette, no alpha,
no interlacing. Rounded corners are done by testing each pixel against the
corner circles, which at icon sizes is both fast enough and exact.
"""

from __future__ import annotations

import struct
import zlib


class Canvas:
    """A plain RGB pixel buffer with the two shapes the icon needs."""

    def __init__(self, width: int, height: int, fill: tuple[int, int, int]):
        self.w, self.h = width, height
        self.px = bytearray(bytes(fill) * (width * height))

    def _set(self, x: int, y: int, colour: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(colour)

    def rounded_rect(
        self,
        x0: float, y0: float, x1: float, y1: float,
        radius: float,
        fill: tuple[int, int, int] | None = None,
        outline: tuple[int, int, int] | None = None,
        width: float = 1.0,
    ) -> None:
        """Fill or stroke a rounded rectangle.

        A pixel is inside when it is inside the inset rectangle, or within
        `radius` of the nearest corner centre. Stroking is the same test run
        twice: inside the outer shape and not inside the shape inset by the
        stroke width.
        """
        def inside(px: float, py: float, ox: float) -> bool:
            ax0, ay0 = x0 + ox, y0 + ox
            ax1, ay1 = x1 - ox, y1 - ox
            if ax1 <= ax0 or ay1 <= ay0:
                return False
            r = max(0.0, min(radius - ox, (ax1 - ax0) / 2, (ay1 - ay0) / 2))
            if not (ax0 <= px <= ax1 and ay0 <= py <= ay1):
                return False
            cx = min(max(px, ax0 + r), ax1 - r)
            cy = min(max(py, ay0 + r), ay1 - r)
            return (px - cx) ** 2 + (py - cy) ** 2 <= r * r + 0.01

        colour = fill if fill is not None else outline
        if colour is None:
            return

        for y in range(int(y0) - 1, int(y1) + 2):
            for x in range(int(x0) - 1, int(x1) + 2):
                px, py = x + 0.5, y + 0.5
                if not inside(px, py, 0.0):
                    continue
                if outline is not None and fill is None and inside(px, py, width):
                    continue          # hollow centre
                self._set(x, y, colour)

    def to_png(self) -> bytes:
        """Signature, IHDR, IDAT, IEND. Filter type 0 on every scanline."""
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride:(y + 1) * stride]

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b"")
        )
