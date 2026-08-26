"""Install the Stream Deck plugin into Elgato's Plugins folder."""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN_DIR = ROOT / "streamdeck" / "com.wallacecandido.mkvtomp4.sdPlugin"
PLUGIN_ID = "com.wallacecandido.mkvtomp4.sdPlugin"


def install_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("APPDATA is not set.")
    return Path(appdata) / "Elgato" / "StreamDeck" / "Plugins" / PLUGIN_ID


def pack_release(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in PLUGIN_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, Path(PLUGIN_ID) / path.relative_to(PLUGIN_DIR))


def main() -> None:
    if not PLUGIN_DIR.is_dir():
        raise SystemExit(f"Missing plugin folder: {PLUGIN_DIR}")
    target = install_dir()
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PLUGIN_DIR, target)
    packed = ROOT / "dist" / "Remuxr.streamDeckPlugin"
    pack_release(packed)
    print(f"Installed plugin to:\n  {target}")
    print("Restart the Stream Deck app, then add Remuxr actions from the action list.")
    print(f"Also packed:\n  {packed}")
    print("The Remuxr desktop app must be running on this computer.")


if __name__ == "__main__":
    main()
