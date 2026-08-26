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
DIST_NAME = "MKV to MP4"
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


def main() -> None:
    ffmpeg_dir = ensure_ffmpeg()
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    sep = ";" if os.name == "nt" else ":"
    add_binary = f"{ffmpeg_dir}{sep}ffmpeg"
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
        str(ROOT / "app.py"),
    ]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)
    exe = ROOT / "dist" / f"{DIST_NAME}.exe"
    print(f"Built: {exe}", flush=True)


if __name__ == "__main__":
    main()
