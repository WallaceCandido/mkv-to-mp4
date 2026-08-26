"""Remux MKV to MP4 with FFmpeg (stream copy, no re-encode)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

COMMON_FFMPEG_PATHS = (
    Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\Program Files\Gyan\FFmpeg\bin\ffmpeg.exe"),
)


def _bundled_ffmpeg() -> Path | None:
    names = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        names.append(base / "ffmpeg" / "ffmpeg.exe")
        names.append(base / "ffmpeg.exe")
    if getattr(sys, "frozen", False):
        names.append(Path(sys.executable).parent / "ffmpeg" / "ffmpeg.exe")
    else:
        names.append(Path(__file__).resolve().parent / "ffmpeg" / "ffmpeg.exe")
        names.append(Path(__file__).resolve().parent / "tools" / "ffmpeg" / "ffmpeg.exe")
    for candidate in names:
        if candidate.is_file():
            return candidate
    return None


def find_ffmpeg() -> str | None:
    bundled = _bundled_ffmpeg()
    if bundled:
        return str(bundled)
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


def output_path_for(
    mkv_path: Path,
    output_dir: Path | None = None,
    watch_folder: Path | None = None,
) -> Path:
    mkv_path = Path(mkv_path)
    if output_dir is None:
        return mkv_path.with_suffix(".mp4")
    output_dir = Path(output_dir)
    if watch_folder and watch_folder in mkv_path.parents:
        relative = mkv_path.relative_to(watch_folder).with_suffix(".mp4")
        return output_dir / relative
    return output_dir / mkv_path.with_suffix(".mp4").name


def remux_mkv_to_mp4(mkv_path: Path, ffmpeg: str, dest: Path | None = None) -> Path:
    """Copy video/audio into an MP4 container. Raises RuntimeError on failure."""
    mkv_path = Path(mkv_path)
    if not mkv_path.is_file():
        raise FileNotFoundError(f"MKV not found: {mkv_path}")

    dest = Path(dest) if dest is not None else output_path_for(mkv_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mkv-to-mp4-") as tmp_dir:
        tmp = Path(tmp_dir) / dest.name
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
            str(tmp),
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
        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise RuntimeError("FFmpeg finished but the MP4 is missing or empty.")
        try:
            shutil.copy2(tmp, dest)
        except PermissionError as exc:
            raise RuntimeError(
                f"Permission denied writing {dest}. "
                "The shared folder is probably read-only, the MP4 is open in another program, "
                "or this Windows user does not have Modify permission. "
                "On the PC that shares the folder, allow Change/Modify for your user, "
                "or set Save MP4s to a local folder on this computer."
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Could not save MP4 to {dest}: {exc}") from exc
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError("The MP4 was remuxed but could not be saved to the destination.")
    return dest
