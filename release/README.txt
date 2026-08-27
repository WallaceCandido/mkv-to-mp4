Remuxr
MKV to MP4. Fast. Simple. Clean.

This zip has everything you need. You do not need Python or FFmpeg installed.


WHAT IS IN THIS FOLDER

  Remuxr.exe               The main app
  Remuxr-StreamDeck.exe    Stream Deck plugin installer (optional)
  README.txt               These instructions


1. RUN THE APP

  1. Double-click Remuxr.exe.
  2. Windows may warn that the app is unrecognized (it is not code-signed).
     Click More info, then Run anyway.
  3. The first launch can take a few seconds while Windows unpacks the app.
  4. Choose a Watch folder (where your .mkv files appear).
  5. If that folder is a read-only network share, uncheck "Save next to the MKV"
     and pick a local folder under Save MP4s to.
  6. Click Start watching.

Files already in the folder are listed but are not remuxed automatically.
Only new .mkv files that appear after you start watching are remuxed on their own.
You can check existing files and click Remux selected to convert them by hand.

The three-dot menu in the top-right opens Settings (show log, Stream Deck connection, dark mode).


2. STREAM DECK (OPTIONAL)

  Remuxr and Stream Deck software must run on the SAME Windows PC.

  1. Install Elgato Stream Deck software if it is not already installed.
  2. Double-click Remuxr-StreamDeck.exe.
  3. Fully quit Stream Deck from the system tray (Quit), then open it again.
  4. Start Remuxr.exe. The window should show Stream Deck: :17321.
     If it says "port busy", close extra copies of Remuxr.
     If it says "off", turn Stream Deck connection on in Settings.
  5. In Stream Deck, open the action list, find Remuxr, and drag Toggle Watch
     onto a key (optional: Start Watch / Stop Watch).
  6. Pick a watch folder in Remuxr, then press the key.

The key shows Idle or Watching. App off means Remuxr is not running.

Stream Deck key titles:
  App off     Remuxr is not running, or is not listening on port 17321
  No folder   Choose a watch folder in Remuxr first
  No FFmpeg   Use this Remuxr.exe (FFmpeg is packed inside)
  No write    The watch folder (and fallback) are not writable


NOTES

  - Remux copies video and audio into an .mp4 container. It does not re-encode,
    so it is fast and quality stays the same.
  - The .mp4 uses the same name as the .mkv.
  - If a file is still being copied, Remuxr waits until its size stops growing.
  - Subtitles are skipped so remux is more likely to succeed.

More information: https://github.com/WallaceCandido/Remuxr
