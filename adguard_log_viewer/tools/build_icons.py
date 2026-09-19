#!/usr/bin/env python3
"""Generate the add-on's ``icon.png`` and ``logo.png``.

Home Assistant shows ``icon.png`` (square, 128x128) in the add-on list and the
sidebar, and ``logo.png`` (wide, 250x100) on the add-on page. Both are drawn
here from a few shapes rather than checked in as opaque binaries, so the mark can
be tweaked without a design tool:

    python tools/build_icons.py

Pure standard library — no Pillow, no build-time dependency. The shapes are
supersampled 4x and averaged, which is enough antialiasing at these sizes.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Home Assistant blue, matching the UI's --primary token.
BLUE = (3, 169, 244)
DARK = (20, 26, 33)
WHITE = (255, 255, 255)

SUPERSAMPLE = 4

Color = tuple[int, int, int]


def write_png(path: Path, width: int, height: int, pixels: list[list[Color]]) -> None:
    """Write a minimal 8-bit RGB PNG."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0 (None)
        for red, green, blue in row:
            raw.extend((red, green, blue))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def blend(bottom: Color, top: Color, alpha: float) -> Color:
    return (
        round(bottom[0] + (top[0] - bottom[0]) * alpha),
        round(bottom[1] + (top[1] - bottom[1]) * alpha),
        round(bottom[2] + (top[2] - bottom[2]) * alpha),
    )


def in_shield(x: float, y: float, cx: float, cy: float, half_w: float, half_h: float) -> bool:
    """A shield: a rounded rectangle whose lower part tapers to a point."""
    dx = (x - cx) / half_w
    dy = (y - cy) / half_h
    if abs(dx) > 1 or abs(dy) > 1:
        return False
    if dy <= 0.15:
        # Upper body, with rounded shoulders.
        corner = 0.72
        if abs(dx) > corner and dy < -corner:
            ox = (abs(dx) - corner) / (1 - corner)
            oy = (-dy - corner) / (1 - corner)
            return ox * ox + oy * oy <= 1
        return True
    # Lower body tapers to the tip.
    taper = 1.0 - ((dy - 0.15) / 0.85) ** 1.45
    return abs(dx) <= taper


def in_bars(x: float, y: float, cx: float, cy: float, unit: float) -> bool:
    """Three stacked bars of decreasing width — a log, abstracted."""
    heights = (-1.15, 0.0, 1.15)
    widths = (1.0, 0.72, 0.44)
    for offset, width in zip(heights, widths, strict=True):
        by = cy + offset * unit * 0.62
        if abs(y - by) <= unit * 0.24 and abs(x - cx) <= unit * width:
            # Rounded ends.
            flat = unit * width - unit * 0.24
            if abs(x - cx) <= flat:
                return True
            ox = (abs(x - cx) - flat) / (unit * 0.24)
            oy = (y - by) / (unit * 0.24)
            return ox * ox + oy * oy <= 1
    return False


def render(width: int, height: int, *, background: Color, shield_scale: float) -> list[list[Color]]:
    pixels: list[list[Color]] = []
    cx, cy = width / 2, height / 2
    half_h = height * shield_scale / 2
    half_w = half_h * 0.82
    unit = half_h * 0.42

    for py in range(height):
        row: list[Color] = []
        for px in range(width):
            shield_hits = 0
            bar_hits = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    x = px + (sx + 0.5) / SUPERSAMPLE
                    y = py + (sy + 0.5) / SUPERSAMPLE
                    if in_shield(x, y, cx, cy, half_w, half_h):
                        shield_hits += 1
                        if in_bars(x, y, cx, cy, unit):
                            bar_hits += 1
            total = SUPERSAMPLE * SUPERSAMPLE
            color = blend(background, BLUE, shield_hits / total)
            if bar_hits:
                color = blend(color, WHITE, bar_hits / total)
            row.append(color)
        pixels.append(row)
    return pixels


def render_logo(width: int, height: int) -> list[list[Color]]:
    """The mark on a wide plate.

    Deliberately just the mark: a wordmark rendered from shapes would read as a
    placeholder, and shipping a font for two words is not worth it. Replace this
    file with a branded logo if you want one — Home Assistant only needs a PNG
    of roughly 250x100.
    """
    pixels = [[DARK for _ in range(width)] for _ in range(height)]
    mark_size = int(height * 0.94)
    mark = render(mark_size, mark_size, background=DARK, shield_scale=0.92)
    left = (width - mark_size) // 2
    top = (height - mark_size) // 2
    for y in range(mark_size):
        for x in range(mark_size):
            pixels[top + y][left + x] = mark[y][x]
    return pixels


def main() -> None:
    icon = render(128, 128, background=DARK, shield_scale=0.86)
    write_png(ROOT / "icon.png", 128, 128, icon)

    logo = render_logo(250, 100)
    write_png(ROOT / "logo.png", 250, 100, logo)

    print(f"Wrote {ROOT / 'icon.png'} (128x128) and {ROOT / 'logo.png'} (250x100)")


if __name__ == "__main__":
    main()
