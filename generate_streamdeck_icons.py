"""Draw Stream Deck key images into the plugin folder."""

from __future__ import annotations

from pathlib import Path

from icons import BLUE, write_png

ROOT = Path(__file__).resolve().parent / "streamdeck" / "com.wallacecandido.mkvtomp4.sdPlugin" / "imgs"
RED = (220, 38, 38, 255)
DARK = (30, 41, 59, 255)
WHITE = (255, 255, 255, 255)


def _canvas(size: int, fill: tuple[int, int, int, int]):
    return [[fill for _ in range(size)] for _ in range(size)]


def _dot(pixels, cx: float, cy: float, radius: float, color, hole: float = 0.0) -> None:
    h = len(pixels)
    w = len(pixels[0])
    for y in range(h):
        for x in range(w):
            d = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
            if hole and d < hole:
                continue
            if d <= radius:
                pixels[y][x] = color
            elif d < radius + 1:
                pass


def _save(name: str, pixels) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    write_png(ROOT / f"{name}.png", pixels)
    # @2x: nearest-neighbor scale
    h, w = len(pixels), len(pixels[0])
    big = [[pixels[y // 2][x // 2] for x in range(w * 2)] for y in range(h * 2)]
    write_png(ROOT / f"{name}@2x.png", big)


def main() -> None:
    for size, suffix in ((72, ""),):
        idle = _canvas(size, DARK)
        _dot(idle, size / 2, size / 2, size * 0.22, WHITE, hole=size * 0.14)
        _save("idle", idle)

        watching = _canvas(size, DARK)
        _dot(watching, size / 2, size / 2, size * 0.22, RED)
        _save("watching", watching)

        toggle = _canvas(size, DARK)
        _dot(toggle, size / 2, size / 2, size * 0.26, BLUE)
        _save("toggle", toggle)

        category = _canvas(size, BLUE)
        _dot(category, size / 2, size / 2, size * 0.2, WHITE)
        _save("category", category)
    print(f"Wrote icons in {ROOT}")


if __name__ == "__main__":
    main()
