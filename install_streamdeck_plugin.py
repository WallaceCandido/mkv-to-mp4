"""Install the Stream Deck plugin into Elgato's Plugins folder."""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

PLUGIN_ID = "com.wallacecandido.mkvtomp4.sdPlugin"


def plugin_source() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "streamdeck" / PLUGIN_ID
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent / "streamdeck" / PLUGIN_ID


def install_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("APPDATA is not set.")
    return Path(appdata) / "Elgato" / "StreamDeck" / "Plugins" / PLUGIN_ID


def pack_release(dest: Path, source: Path | None = None) -> None:
    src = source or plugin_source()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_file():
                zf.write(path, Path(PLUGIN_ID) / path.relative_to(src))


def _notify(title: str, message: str, *, error: bool = False) -> None:
    printed = False
    try:
        if sys.stdout and sys.stdout.isatty():
            print(message)
            printed = True
    except OSError:
        pass
    if printed and not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 if error else 0x40)
    except Exception:
        if not printed:
            print(message)


def main() -> None:
    source = plugin_source()
    if not source.is_dir():
        _notify("Remuxr Stream Deck", f"Missing plugin folder:\n{source}", error=True)
        raise SystemExit(1)
    try:
        target = install_dir()
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    except OSError as exc:
        _notify(
            "Remuxr Stream Deck",
            "Could not install the plugin. Fully quit Stream Deck from the "
            f"system tray, then run this installer again.\n\n{exc}",
            error=True,
        )
        raise SystemExit(1) from exc

    if not getattr(sys, "frozen", False):
        packed = Path(__file__).resolve().parent / "dist" / "Remuxr.streamDeckPlugin"
        pack_release(packed, source)
        extra = f"\n\nAlso packed:\n{packed}"
    else:
        extra = ""

    _notify(
        "Remuxr Stream Deck",
        "Plugin installed.\n\n"
        "1. Quit Stream Deck from the system tray, then open it again.\n"
        "2. Add Remuxr actions from the action list.\n"
        "3. Keep the Remuxr app running on this PC."
        f"{extra}",
    )


if __name__ == "__main__":
    main()
