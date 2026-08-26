# mkv-to-mp4

A simple desktop app that remuxes `.mkv` files to `.mp4` using FFmpeg.

**Remux** copies the existing video and audio into a new container. It does not re-encode, so it is fast and quality stays the same.

## What it does

- You pick a folder to watch.
- Files that are **already in that folder** are listed, but they are **not** remuxed automatically.
- **New** `.mkv` files that appear after watching starts are remuxed to `.mp4` in the same folder.
- You can select any existing `.mkv` and remux it by hand.

## Requirements

- Python 3.12+ (tkinter is included with the official Windows installer)
- [FFmpeg](https://ffmpeg.org/) on your PATH

## Run

```powershell
python app.py
```

Or double-click `run.bat`.

## Windows executable

From this folder:

```powershell
python build_exe.py
```

That creates a single file: `dist\MKV to MP4.exe`. You can copy just that file. FFmpeg is packed inside it; Windows unpacks it to a temp folder when the app starts, so the first launch is a bit slower.

## Notes

- The `.mp4` is written next to the `.mkv` with the same name.
- If a file is still being copied into the folder, the app waits until its size stops growing before remuxing.
- Some audio or subtitle formats cannot live in MP4. The app copies video and audio streams; subtitles are skipped so remux is more likely to succeed.
