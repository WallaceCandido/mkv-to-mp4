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

The gear in the top-right opens **Settings**. You can hide or show the log, turn the Stream Deck connection off, and switch dark mode. Those choices are remembered the next time you open the app.

## Windows executable

From this folder:

```powershell
python build_exe.py
```

That creates a single file: `dist\MKV to MP4.exe`. You can copy just that file. FFmpeg is packed inside it; Windows unpacks it to a temp folder when the app starts, so the first launch is a bit slower.

## Stream Deck

You can start and stop folder watching from an Elgato Stream Deck. The **MKV to MP4 app** and **Stream Deck software** must run on the **same Windows PC**.

### What you need

- Stream Deck software installed
- This app running (`python app.py` or the `.exe`)
- A watch folder already chosen in the app
- The window should show **Stream Deck: :17321** (if it says **port busy**, close extra copies of the app). If the label says **Stream Deck: off**, turn the connection back on in Settings.

### Install the plugin (from source)

In the project folder:

```powershell
python generate_streamdeck_icons.py
python install_streamdeck_plugin.py
```

That copies the plugin to:

`%APPDATA%\Elgato\StreamDeck\Plugins\com.wallacecandido.mkvtomp4.sdPlugin`

Fully quit Stream Deck (system tray → **Quit**), then open it again.

### Add keys

1. In Stream Deck, open the action list.
2. Find the **MKV to MP4** category.
3. Drag **Toggle Watch** onto a key (optional: **Start Watch** and **Stop Watch**).

The key shows **Idle** or **Watching**. If the desktop app is not running, it shows **App off**.

### How to use it

1. Open MKV to MP4 and pick your watch folder (and an MP4 output folder if the watch folder is read-only).
2. Press **Toggle Watch** on the Stream Deck.
3. Confirm the app log says `Stream Deck started watching.` and that **Start watching** is disabled.

If the watch folder is not writable (common on a network share), the app saves MP4s under `Videos\MKV to MP4` instead and notes that in the log.

### Another PC

Copy the plugin pack (created by `install_streamdeck_plugin.py`):

`dist\MKV-to-MP4.streamDeckPlugin`

Double-click it on the other PC, restart Stream Deck, and run the MKV to MP4 app there. The Stream Deck must be attached to that same computer.

### Troubleshooting

| Key title | Meaning |
| --- | --- |
| App off | The desktop app is not running, or is not listening on port 17321 |
| No folder | Choose a watch folder in the app first |
| No FFmpeg | FFmpeg was not found (use the bundled `.exe` build, or install FFmpeg) |
| No write | Windows could not create files in the watch folder or a local fallback |

The app talks to the plugin at `http://127.0.0.1:17321`. Nothing is exposed on the network.

## Notes

- The `.mp4` is written next to the `.mkv` with the same name.
- If a file is still being copied into the folder, the app waits until its size stops growing before remuxing.
- Some audio or subtitle formats cannot live in MP4. The app copies video and audio streams; subtitles are skipped so remux is more likely to succeed.
