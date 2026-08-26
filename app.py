"""Desktop app: watch a folder for new MKVs and remux them to MP4."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from icons import IconSet
from remux import find_ffmpeg, output_path_for, remux_mkv_to_mp4

POLL_SECONDS = 2.0
STABLE_CHECKS = 2
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "mkv-to-mp4"
CONFIG_PATH = APP_DIR / "config.json"

STATUS_EXISTING = "Existing (manual only)"
STATUS_DETECTED = "New — waiting"
STATUS_REMUXING = "Remuxing…"
STATUS_DONE = "Remuxed"
STATUS_FAILED = "Failed"
STATUS_SKIPPED = "MP4 already exists"


def load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_mkv_files(folder: Path, recursive: bool) -> list[Path]:
    if not folder.is_dir():
        return []
    if recursive:
        return sorted(p for p in folder.rglob("*.mkv") if p.is_file())
    return sorted(p for p in folder.glob("*.mkv") if p.is_file())


def format_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{num} B"
        num /= 1024
    return f"{num:.1f} TB"


LIST_COLUMNS = ("name", "status", "size", "date")
COLUMN_TITLES = {"name": "File", "status": "Status", "size": "Size", "date": "Date"}


def display_name(path: Path, folder: Path | None) -> str:
    if folder and folder in path.parents:
        try:
            return str(path.relative_to(folder))
        except ValueError:
            return path.name
    return path.name


def file_row(
    path: Path, folder: Path | None, status: str
) -> tuple[tuple[str, str, str, str, str], dict[str, object]]:
    size_bytes = 0
    mtime = 0.0
    exists = path.is_file()
    if exists:
        try:
            stat = path.stat()
            size_bytes = stat.st_size
            mtime = stat.st_mtime
        except OSError:
            exists = False
    name = display_name(path, folder)
    values = (
        name,
        status,
        format_size(size_bytes) if exists else "",
        datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if exists else "",
        "",
    )
    keys = {
        "name": name.casefold(),
        "status": status.casefold(),
        "size": size_bytes,
        "date": mtime,
    }
    return values, keys


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MKV to MP4")
        self.minsize(880, 520)
        self.geometry("1020x620")

        self.ffmpeg = find_ffmpeg()
        self.watch_folder = tk.StringVar(value=load_config().get("watch_folder", ""))
        self.recursive = tk.BooleanVar(value=False)
        self.watching = False

        self.baseline: set[str] = set()
        self.file_status: dict[str, str] = {}
        self.size_history: dict[str, list[int]] = {}
        self.queued: set[str] = set()
        self.jobs: queue.Queue[tuple[str, Path]] = queue.Queue()
        self.ui_events: queue.Queue[tuple] = queue.Queue()
        self.sort_column = "name"
        self.sort_reverse = False
        self.sort_keys: dict[str, dict[str, object]] = {}
        self.checked: set[str] = set()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self._drain_ui_events)
        self._refresh_ffmpeg_label()

        if self.watch_folder.get():
            self.refresh_file_list(initial=True)

    def _build(self) -> None:
        self.icons = IconSet(self)
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=30, indent=0)
        style.configure("Treeview.Heading", padding=(8, 6))
        try:
            style.layout(
                "Treeview.Item",
                [
                    (
                        "Treeitem.padding",
                        {
                            "sticky": "nswe",
                            "children": [
                                ("Treeitem.image", {"side": "left", "sticky": ""}),
                                ("Treeitem.text", {"side": "left", "sticky": ""}),
                            ],
                        },
                    )
                ],
            )
        except tk.TclError:
            pass

        pad = {"padx": 12, "pady": 6}

        header = ttk.Frame(self)
        header.pack(fill="x", **pad)
        ttk.Label(header, text="Watch folder").pack(anchor="w")

        row = ttk.Frame(header)
        row.pack(fill="x", pady=(4, 0))
        ttk.Entry(row, textvariable=self.watch_folder).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self.browse_folder).pack(side="left", padx=(8, 0))

        controls = ttk.Frame(self)
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="Start watching", command=self.start_watching)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="Stop", command=self.stop_watching, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            controls,
            text="Include subfolders",
            variable=self.recursive,
            command=self.on_recursive_toggle,
        ).pack(side="left", padx=(16, 0))
        self.ffmpeg_label = ttk.Label(controls, text="")
        self.ffmpeg_label.pack(side="right")

        hint = ttk.Label(
            self,
            text="Existing .mkv files are listed but never remuxed automatically. "
            "Only files that appear after you start watching are remuxed on their own.",
            wraplength=860,
        )
        hint.pack(fill="x", padx=12)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=6)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=(*LIST_COLUMNS, "spacer"),
            show="tree headings",
            selectmode="none",
        )
        self.tree.column("#0", width=42, minwidth=42, stretch=False, anchor="center")
        self.tree.column("name", width=280, minwidth=120, stretch=True)
        self.tree.column("status", width=280, minwidth=160, stretch=False)
        self.tree.column("size", width=90, minwidth=70, stretch=False, anchor="e")
        self.tree.column("date", width=140, minwidth=120, stretch=False)
        self.tree.heading("spacer", text="")
        self.tree.column("spacer", width=0, minwidth=0, stretch=True)
        self.tree.tag_configure("checked", background="#e8f0fe")
        self._refresh_headings()
        self.tree.bind("<Button-1>", self._on_tree_click)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="Remux selected", command=self.remux_selected).pack(side="left")
        ttk.Button(actions, text="Select all", command=lambda: self._set_all_checked(True)).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Clear", command=lambda: self._set_all_checked(False)).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Refresh list", command=lambda: self.refresh_file_list()).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Open folder", command=self.open_folder).pack(side="left", padx=(8, 0))

        ttk.Label(self, text="Log").pack(anchor="w", padx=12)
        self.log = tk.Text(self, height=8, wrap="word", state="disabled")
        self.log.pack(fill="x", padx=12, pady=(0, 12))

        threading.Thread(target=self._worker_loop, daemon=True).start()

    def _refresh_headings(self) -> None:
        rows = self.tree.get_children("")
        checked_rows = [iid for iid in rows if iid in self.checked]
        if not rows or not checked_rows:
            header_icon = self.icons.unchecked
        elif len(checked_rows) == len(rows):
            header_icon = self.icons.checked
        else:
            header_icon = self.icons.mixed
        self.tree.heading("#0", text="", image=header_icon, command=self._toggle_select_all)
        for column in LIST_COLUMNS:
            if column == self.sort_column:
                mark = self.icons.sort_desc if self.sort_reverse else self.icons.sort_asc
            else:
                mark = self.icons.sort_none
            self.tree.heading(
                column,
                text=COLUMN_TITLES[column],
                image=mark,
                command=lambda c=column: self.sort_by(c),
            )

    def _on_tree_click(self, event: tk.Event) -> str | None:
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            if self.tree.identify_column(event.x) == "#0":
                self._toggle_select_all()
                return "break"
            return None
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        self._toggle_check(row)
        return "break"

    def _toggle_check(self, iid: str) -> None:
        self._set_checked(iid, iid not in self.checked)

    def _toggle_select_all(self) -> None:
        rows = self.tree.get_children("")
        if not rows:
            return
        self._set_all_checked(not all(iid in self.checked for iid in rows))

    def _set_all_checked(self, on: bool) -> None:
        for iid in self.tree.get_children(""):
            self._set_checked(iid, on, refresh_heading=False)
        self._refresh_headings()
        if self.sort_column == "picked":
            self._apply_sort()

    def _set_checked(self, iid: str, on: bool, *, refresh_heading: bool = True) -> None:
        if on:
            self.checked.add(iid)
        else:
            self.checked.discard(iid)
        if self.tree.exists(iid):
            icon = self.icons.checked if on else self.icons.unchecked
            self.tree.item(iid, image=icon, tags=("checked",) if on else ())
            if iid in self.sort_keys:
                self.sort_keys[iid]["picked"] = 1 if on else 0
        if refresh_heading:
            self._refresh_headings()
            if self.sort_column == "picked":
                self._apply_sort()

    def sort_by(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self._refresh_headings()
        self._apply_sort()

    def _apply_sort(self) -> None:
        rows = list(self.tree.get_children(""))
        rows.sort(
            key=lambda iid: self.sort_keys.get(iid, {}).get(self.sort_column, ""),
            reverse=self.sort_reverse,
        )
        for index, iid in enumerate(rows):
            self.tree.move(iid, "", index)

    def _put_row(self, path: Path, status: str, *, apply_sort: bool = True) -> None:
        key = str(path)
        values, keys = file_row(path, self.folder_path(), status)
        picked = key in self.checked
        keys = {"picked": 1 if picked else 0, **keys}
        self.sort_keys[key] = keys
        tags = ("checked",) if picked else ()
        icon = self.icons.checked if picked else self.icons.unchecked
        if self.tree.exists(key):
            self.tree.item(key, values=values, image=icon, text="", tags=tags)
        else:
            self.tree.insert("", "end", iid=key, values=values, image=icon, text="", tags=tags)
        if apply_sort:
            self._apply_sort()

    def _refresh_ffmpeg_label(self) -> None:
        if self.ffmpeg:
            self.ffmpeg_label.configure(text="FFmpeg: found")
        else:
            self.ffmpeg_label.configure(text="FFmpeg: not found")

    def log_line(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def folder_path(self) -> Path | None:
        raw = self.watch_folder.get().strip()
        if not raw:
            return None
        return Path(raw)

    def browse_folder(self) -> None:
        initial = self.watch_folder.get() or str(Path.home())
        chosen = filedialog.askdirectory(title="Choose a folder to watch", initialdir=initial)
        if not chosen:
            return
        self.watch_folder.set(chosen)
        save_config({"watch_folder": chosen})
        if self.watching:
            self.stop_watching()
        self.refresh_file_list(initial=True)

    def on_recursive_toggle(self) -> None:
        if self.watching:
            self.stop_watching()
            self.log_line("Stopped watching because the subfolder option changed.")
        self.refresh_file_list(initial=True)

    def refresh_file_list(self, initial: bool = False) -> None:
        folder = self.folder_path()
        self.tree.delete(*self.tree.get_children())
        self.sort_keys.clear()
        if not folder or not folder.is_dir():
            self.checked.clear()
            self._refresh_headings()
            return
        files = list_mkv_files(folder, self.recursive.get())
        present = {str(path) for path in files}
        self.checked &= present
        for path in files:
            key = str(path)
            if initial:
                self.file_status[key] = STATUS_EXISTING
            elif key not in self.file_status:
                self.file_status[key] = STATUS_DETECTED if self.watching else STATUS_EXISTING
            status = self.file_status.get(key, STATUS_EXISTING)
            if status == STATUS_EXISTING and output_path_for(path).is_file():
                status = f"{STATUS_EXISTING} · {STATUS_SKIPPED}"
            self._put_row(path, status, apply_sort=False)
        self._apply_sort()
        self._refresh_headings()

    def start_watching(self) -> None:
        folder = self.folder_path()
        if not folder or not folder.is_dir():
            messagebox.showerror("Folder needed", "Choose an existing folder to watch.")
            return
        if not self.ffmpeg:
            self.ffmpeg = find_ffmpeg()
            self._refresh_ffmpeg_label()
        if not self.ffmpeg:
            messagebox.showerror(
                "FFmpeg not found",
                "Install FFmpeg and make sure it is on your PATH, then try again.",
            )
            return

        save_config({"watch_folder": str(folder)})
        existing = list_mkv_files(folder, self.recursive.get())
        self.baseline = {str(p) for p in existing}
        self.file_status = {str(p): STATUS_EXISTING for p in existing}
        self.size_history.clear()
        self.queued.clear()
        self.watching = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.refresh_file_list()
        self.log_line(f"Watching {folder}")
        self.log_line(
            f"Found {len(existing)} existing .mkv file(s). They will not be remuxed unless you select them."
        )
        threading.Thread(target=self._watch_loop, daemon=True).start()

    def stop_watching(self) -> None:
        self.watching = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.log_line("Stopped watching.")

    def open_folder(self) -> None:
        folder = self.folder_path()
        if folder and folder.is_dir():
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showerror("Folder needed", "Choose a folder first.")

    def selected_paths(self) -> list[Path]:
        return [Path(iid) for iid in self.tree.get_children("") if iid in self.checked]

    def remux_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo(
                "Nothing selected",
                "Click the boxes on the left to choose one or more .mkv files.",
            )
            return
        if not self.ffmpeg:
            self.ffmpeg = find_ffmpeg()
            self._refresh_ffmpeg_label()
        if not self.ffmpeg:
            messagebox.showerror("FFmpeg not found", "Install FFmpeg and make sure it is on your PATH.")
            return
        for path in paths:
            self._enqueue(path, reason="manual")

    def _enqueue(self, path: Path, reason: str) -> None:
        key = str(path)
        if key in self.queued:
            return
        self.queued.add(key)
        self.file_status[key] = STATUS_REMUXING
        self._set_row_status(path, STATUS_REMUXING)
        self.jobs.put((reason, path))
        self.log_line(f"Queued ({reason}): {path.name}")

    def _set_row_status(self, path: Path, status: str) -> None:
        self._put_row(path, status)

    def _watch_loop(self) -> None:
        while self.watching:
            folder = self.folder_path()
            if folder and folder.is_dir():
                try:
                    files = list_mkv_files(folder, self.recursive.get())
                except OSError as exc:
                    self.ui_events.put(("log", f"Could not read folder: {exc}"))
                    time.sleep(POLL_SECONDS)
                    continue
                for path in files:
                    key = str(path)
                    if key in self.baseline or key in self.queued:
                        continue
                    if self.file_status.get(key) in {STATUS_DONE, STATUS_REMUXING, STATUS_FAILED}:
                        continue
                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue
                    history = self.size_history.setdefault(key, [])
                    history.append(size)
                    if len(history) > STABLE_CHECKS + 1:
                        history.pop(0)
                    if len(history) < STABLE_CHECKS:
                        self.file_status[key] = STATUS_DETECTED
                        self.ui_events.put(("upsert", path, STATUS_DETECTED))
                        continue
                    if len(set(history[-STABLE_CHECKS:])) != 1:
                        self.file_status[key] = STATUS_DETECTED
                        self.ui_events.put(("upsert", path, STATUS_DETECTED))
                        continue
                    if output_path_for(path).is_file():
                        self.file_status[key] = STATUS_SKIPPED
                        self.ui_events.put(("upsert", path, STATUS_SKIPPED))
                        self.ui_events.put(("log", f"Skipped (MP4 exists): {path.name}"))
                        continue
                    self.ui_events.put(("enqueue_auto", path))
            time.sleep(POLL_SECONDS)

    def _worker_loop(self) -> None:
        while True:
            reason, path = self.jobs.get()
            try:
                remux_mkv_to_mp4(path, self.ffmpeg)  # type: ignore[arg-type]
                self.ui_events.put(("done", path, reason))
            except Exception as exc:  # noqa: BLE001 — show any remux failure in the UI
                self.ui_events.put(("failed", path, str(exc)))
            finally:
                self.jobs.task_done()

    def _drain_ui_events(self) -> None:
        while True:
            try:
                event = self.ui_events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "log":
                self.log_line(event[1])
            elif kind == "upsert":
                path, status = event[1], event[2]
                self._put_row(path, status)
            elif kind == "enqueue_auto":
                self._enqueue(event[1], reason="new file")
            elif kind == "done":
                path, reason = event[1], event[2]
                key = str(path)
                self.queued.discard(key)
                self.file_status[key] = STATUS_DONE
                self._set_row_status(path, STATUS_DONE)
                out = output_path_for(path)
                self.log_line(f"Finished ({reason}): {out.name}")
            elif kind == "failed":
                path, err = event[1], event[2]
                key = str(path)
                self.queued.discard(key)
                self.file_status[key] = STATUS_FAILED
                self._set_row_status(path, STATUS_FAILED)
                self.log_line(f"Failed: {path.name} — {err}")
        self.after(200, self._drain_ui_events)

    def on_close(self) -> None:
        self.watching = False
        folder = self.watch_folder.get().strip()
        if folder:
            save_config({"watch_folder": folder})
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
