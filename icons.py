"""Small PNG icons for checkboxes and sort chevrons."""

from __future__ import annotations

import base64
import math
import struct
import zlib
import tkinter as tk
from pathlib import Path

BLUE = (168, 85, 247, 255)
WHITE = (255, 255, 255, 255)
BORDER = (148, 163, 184, 255)
MUTED = (148, 163, 184, 220)
FAINT = (148, 163, 184, 110)


def _png(width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def _blank(w: int, h: int) -> list[list[tuple[int, int, int, int]]]:
    return [[(0, 0, 0, 0) for _ in range(w)] for _ in range(h)]


def _blend(px: tuple[int, int, int, int], color: tuple[int, int, int, int], cover: float) -> tuple[int, int, int, int]:
    cover = max(0.0, min(1.0, cover))
    if cover <= 0:
        return px
    sr, sg, sb, sa = color
    src_a = (sa / 255.0) * cover
    dr, dg, db, da = px
    dst_a = da / 255.0
    out_a = src_a + dst_a * (1 - src_a)
    if out_a <= 0:
        return (0, 0, 0, 0)
    r = (sr * src_a + dr * dst_a * (1 - src_a)) / out_a
    g = (sg * src_a + dg * dst_a * (1 - src_a)) / out_a
    b = (sb * src_a + db * dst_a * (1 - src_a)) / out_a
    return (int(r), int(g), int(b), int(out_a * 255))


def _rounded_rect_cover(x: float, y: float, x0: float, y0: float, x1: float, y1: float, radius: float) -> float:
    if x < x0:
        cx = x0 + radius
        px = x0 - x
    elif x > x1:
        cx = x1 - radius
        px = x - x1
    else:
        cx = x
        px = 0.0
    if y < y0:
        cy = y0 + radius
        py = y0 - y
    elif y > y1:
        cy = y1 - radius
        py = y - y1
    else:
        cy = y
        py = 0.0
    if px == 0 and py == 0:
        return 1.0
    if px > 0 and py > 0:
        dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - radius
    elif px > 0:
        dist = px
        if y < y0 + radius or y > y1 - radius:
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - radius
    else:
        dist = py
        if x < x0 + radius or x > x1 - radius:
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - radius
    if dist <= 0:
        return 1.0
    if dist >= 1:
        return 0.0
    return 1.0 - dist


def _stamp_round_rect(
    pixels: list[list[tuple[int, int, int, int]]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: float,
    fill: tuple[int, int, int, int] | None,
    stroke: tuple[int, int, int, int] | None,
    stroke_width: float = 1.4,
) -> None:
    h = len(pixels)
    w = len(pixels[0])
    for y in range(h):
        for x in range(w):
            inner = _rounded_rect_cover(x + 0.5, y + 0.5, x0, y0, x1, y1, radius)
            if fill and inner:
                pixels[y][x] = _blend(pixels[y][x], fill, inner)
            if stroke:
                outer = _rounded_rect_cover(
                    x + 0.5,
                    y + 0.5,
                    x0 - stroke_width * 0.15,
                    y0 - stroke_width * 0.15,
                    x1 + stroke_width * 0.15,
                    y1 + stroke_width * 0.15,
                    radius + 0.2,
                )
                ring = max(0.0, outer - _rounded_rect_cover(x + 0.5, y + 0.5, x0 + stroke_width, y0 + stroke_width, x1 - stroke_width, y1 - stroke_width, max(0.5, radius - stroke_width)))
                pixels[y][x] = _blend(pixels[y][x], stroke, ring)


def _dist_seg(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    vx, vy = x2 - x1, y2 - y1
    length = vx * vx + vy * vy
    if length == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / length))
    return ((px - (x1 + t * vx)) ** 2 + (py - (y1 + t * vy)) ** 2) ** 0.5


def _stroke_polyline(
    pixels: list[list[tuple[int, int, int, int]]],
    points: list[tuple[float, float]],
    color: tuple[int, int, int, int],
    width: float,
) -> None:
    h = len(pixels)
    w = len(pixels[0])
    half = width / 2
    for y in range(h):
        for x in range(w):
            d = min(_dist_seg(x + 0.5, y + 0.5, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1]) for i in range(len(points) - 1))
            cover = max(0.0, min(1.0, half + 0.55 - d))
            if cover:
                pixels[y][x] = _blend(pixels[y][x], color, cover)


def _photo(root: tk.Misc, pixels: list[list[tuple[int, int, int, int]]]) -> tk.PhotoImage:
    png = _png(len(pixels[0]), len(pixels), pixels)
    return tk.PhotoImage(master=root, data=base64.b64encode(png))


def checkbox(
    root: tk.Misc,
    *,
    checked: bool,
    mixed: bool = False,
    size: int = 18,
    empty_fill: tuple[int, int, int, int] = (255, 255, 255, 230),
) -> tk.PhotoImage:
    pixels = _blank(size, size)
    pad = 1.6
    _stamp_round_rect(
        pixels,
        pad,
        pad,
        size - 1 - pad,
        size - 1 - pad,
        radius=4.2,
        fill=BLUE if (checked or mixed) else empty_fill,
        stroke=None if (checked or mixed) else BORDER,
        stroke_width=1.35,
    )
    if mixed:
        mid = size / 2
        _stroke_polyline(pixels, [(4.2, mid), (size - 4.2, mid)], WHITE, 1.8)
    elif checked:
        _stroke_polyline(pixels, [(4.2, 9.2), (7.4, 12.3), (13.6, 5.4)], WHITE, 1.85)
    return _photo(root, pixels)


def sort_mark(root: tk.Misc, *, state: str, size: int = 12) -> tk.PhotoImage:
    """state: none | asc | desc"""
    w, h = size, size + 4
    pixels = _blank(w, h)
    top = [(2.2, 5.2), (w / 2, 1.6), (w - 2.2, 5.2)]
    bottom = [(2.2, h - 5.2), (w / 2, h - 1.6), (w - 2.2, h - 5.2)]
    if state == "asc":
        _stroke_polyline(pixels, top, BLUE, 1.7)
        _stroke_polyline(pixels, bottom, FAINT, 1.5)
    elif state == "desc":
        _stroke_polyline(pixels, top, FAINT, 1.5)
        _stroke_polyline(pixels, bottom, BLUE, 1.7)
    else:
        _stroke_polyline(pixels, top, MUTED, 1.5)
        _stroke_polyline(pixels, bottom, MUTED, 1.5)
    return _photo(root, pixels)


def write_png(path: Path, pixels: list[list[tuple[int, int, int, int]]]) -> None:
    Path(path).write_bytes(_png(len(pixels[0]), len(pixels), pixels))


def gear_icon(
    root: tk.Misc,
    *,
    size: int = 20,
    color: tuple[int, int, int, int] = (71, 85, 105, 255),
) -> tk.PhotoImage:
    pixels = _blank(size, size)
    cx = cy = size / 2
    outer = size * 0.28
    hole = size * 0.12
    tooth = size * 0.11
    for y in range(size):
        for x in range(size):
            px, py = x + 0.5 - cx, y + 0.5 - cy
            dist = (px * px + py * py) ** 0.5
            cover = 0.0
            if hole < dist <= outer:
                cover = 1.0
            elif dist <= hole:
                cover = max(0.0, 1.0 - (hole - dist))
            for i in range(6):
                a = i * math.pi / 3
                tx = math.cos(a) * (outer + tooth * 0.15)
                ty = math.sin(a) * (outer + tooth * 0.15)
                dx, dy = px - tx, py - ty
                along = dx * math.cos(a) + dy * math.sin(a)
                across = -dx * math.sin(a) + dy * math.cos(a)
                if abs(across) <= tooth * 0.55 and 0 <= along <= tooth * 1.15:
                    cover = max(cover, 1.0)
            if cover:
                pixels[y][x] = _blend(pixels[y][x], color, min(1.0, cover))
    return _photo(root, pixels)


class IconSet:
    def __init__(self, root: tk.Misc, *, dark: bool = False) -> None:
        empty = (38, 38, 38, 255) if dark else (255, 255, 255, 230)
        gear = (212, 212, 212, 255) if dark else (82, 82, 82, 255)
        self.unchecked = checkbox(root, checked=False, empty_fill=empty)
        self.checked = checkbox(root, checked=True)
        self.mixed = checkbox(root, checked=False, mixed=True)
        self.sort_none = sort_mark(root, state="none")
        self.sort_asc = sort_mark(root, state="asc")
        self.sort_desc = sort_mark(root, state="desc")
        self.gear = gear_icon(root, color=gear)
