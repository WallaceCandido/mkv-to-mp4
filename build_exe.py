"""Build a single-file Windows executable with FFmpeg packed inside."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from remux import find_ffmpeg

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools" / "ffmpeg"
DIST_NAME = "Remuxr"
ESSENTIALS_ZIP = (
    "https://github.com/GyanD/codexffmpeg/releases/download/9.0.1/"
    "ffmpeg-9.0.1-essentials_build.zip"
)


def copy_ffmpeg_from_install(dest: Path) -> None:
    source = find_ffmpeg()
    if not source:
        raise FileNotFoundError("FFmpeg not found. Install it or let the build download it.")
    src_dir = Path(source).parent
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "ffmpeg.exe", dest / "ffmpeg.exe")
    for dll in src_dir.glob("*.dll"):
        shutil.copy2(dll, dest / dll.name)


def download_essentials(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = ROOT / "tools" / "ffmpeg-essentials.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {ESSENTIALS_ZIP}")
    urllib.request.urlretrieve(ESSENTIALS_ZIP, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.replace("\\", "/").endswith("/bin/ffmpeg.exe")]
        if not members:
            raise FileNotFoundError("ffmpeg.exe was not inside the downloaded zip.")
        bin_prefix = members[0].rsplit("ffmpeg.exe", 1)[0]
        for name in zf.namelist():
            if not name.startswith(bin_prefix) or name.endswith("/"):
                continue
            filename = Path(name).name
            if filename.lower() != "ffmpeg.exe":
                continue
            with zf.open(name) as src, open(dest / "ffmpeg.exe", "wb") as out:
                shutil.copyfileobj(src, out)
    zip_path.unlink(missing_ok=True)


def ensure_ffmpeg() -> Path:
    bundled = TOOLS / "ffmpeg.exe"
    if bundled.is_file():
        return TOOLS
    print("Preparing FFmpeg for the app bundle…", flush=True)
    try:
        download_essentials(TOOLS)
    except Exception as exc:
        print(f"Download failed ({exc}); copying the FFmpeg already on this PC.")
        copy_ffmpeg_from_install(TOOLS)
    if not (TOOLS / "ffmpeg.exe").is_file():
        raise FileNotFoundError("Could not prepare ffmpeg.exe")
    return TOOLS


def make_app_icon() -> Path | None:
    png = ROOT / "assets" / "remuxr_logo.png"
    ico = ROOT / "assets" / "remuxr.ico"
    if not png.is_file():
        return ico if ico.is_file() else None
    try:
        from PIL import Image
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "pillow"], check=True)
        from PIL import Image

    img = Image.open(png).convert("RGBA")
    pixels = img.load()
    width, height = img.size
    min_x, min_y, max_x, max_y = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 24 and (red + green + blue) > 48:
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x > min_x:
        pad = int(max(max_x - min_x, max_y - min_y) * 0.08)
        cropped = img.crop(
            (
                max(0, min_x - pad),
                max(0, min_y - pad),
                min(width, max_x + 1 + pad),
                min(height, max_y + 1 + pad),
            )
        )
    else:
        cropped = img
    side = max(cropped.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(
        cropped,
        ((side - cropped.size[0]) // 2, (side - cropped.size[1]) // 2),
        cropped,
    )
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    canvas.save(ico, format="ICO", sizes=sizes)
    print(f"Wrote square icon {ico} from cropped logo {canvas.size}", flush=True)
    return ico


def _refresh_windows_icons() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except OSError:
        pass
    ie4 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "ie4uinit.exe"
    if ie4.is_file():
        subprocess.run([str(ie4), "-show"], check=False, capture_output=True)


def main() -> None:
    ffmpeg_dir = ensure_ffmpeg()
    icon = make_app_icon()
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    sep = ";" if os.name == "nt" else ":"
    add_binary = f"{ffmpeg_dir}{sep}ffmpeg"
    add_assets = f"{ROOT / 'assets'}{sep}assets"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name",
        DIST_NAME,
        "--add-binary",
        add_binary,
        "--add-data",
        add_assets,
    ]
    if icon and icon.is_file():
        cmd.extend(["--icon", str(icon)])
    cmd.append(str(ROOT / "app.py"))
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)
    exe = ROOT / "dist" / f"{DIST_NAME}.exe"
    # Write through a new filename so Explorer does not keep a cached icon for this path.
    fresh = ROOT / "dist" / f"{DIST_NAME}-fresh.exe"
    if exe.is_file():
        shutil.copy2(exe, fresh)
        try:
            exe.unlink()
            fresh.replace(exe)
        except OSError:
            print(f"Could not replace {exe}; left a copy at {fresh}", flush=True)
            exe = fresh
    _refresh_windows_icons()
    print(f"Built: {exe}", flush=True)


if __name__ == "__main__":
    main()
