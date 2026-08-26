"""Remux MKV to MP4 with FFmpeg (stream copy, no re-encode)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

COMMON_FFMPEG_PATHS = (
    Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\Program Files\Gyan\FFmpeg\bin\ffmpeg.exe"),
)


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in COMMON_FFMPEG_PATHS:
        if candidate.is_file():
            return str(candidate)
    winget = Path.home() / r"AppData\Local\Microsoft\WinGet\Packages"
    if winget.is_dir():
        matches = sorted(winget.rglob("ffmpeg.exe"))
        if matches:
            return str(matches[0])
    return None


def output_path_for(mkv_path: Path) -> Path:
    return mkv_path.with_suffix(".mp4")


def remux_mkv_to_mp4(mkv_path: Path, ffmpeg: str) -> None:
    """Copy video/audio into an MP4 container. Raises RuntimeError on failure."""
    mkv_path = Path(mkv_path)
    if not mkv_path.is_file():
        raise FileNotFoundError(f"MKV not found: {mkv_path}")

    dest = output_path_for(mkv_path)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(mkv_path),
        "-map",
        "0:v:0?",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown FFmpeg error").strip()
        raise RuntimeError(err or f"FFmpeg exited with code {result.returncode}")
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError("FFmpeg finished but the MP4 is missing or empty.")
