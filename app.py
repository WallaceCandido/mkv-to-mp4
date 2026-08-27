"""Desktop app: watch a folder for new MKVs and remux them to MP4."""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from icons import IconSet
from remux import find_ffmpeg, output_path_for, remux_mkv_to_mp4
from streamdeck_api import DEFAULT_PORT, StreamDeckApi
from widgets import FONT, FONT_LOG, FONT_SMALL, Field, FlatButton, IconCheck, flatten_tree_style

POLL_SECONDS = 2.0
STABLE_CHECKS = 2
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "mkv-to-mp4"
CONFIG_PATH = APP_DIR / "config.json"
APP_NAME = "Remuxr"


def asset_path(name: str) -> Path:
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(Path(meipass) / "assets")
        bases.append(Path(meipass))
    bases.append(Path(__file__).resolve().parent / "assets")
    for base in bases:
        path = base / name
        if path.is_file():
            return path
    return bases[-1] / name

STATUS_EXISTING = "Existing (manual only)"
STATUS_DETECTED = "New — waiting"
STATUS_REMUXING = "Remuxing…"
STATUS_DONE = "Remuxed"
STATUS_FAILED = "Failed"
STATUS_SKIPPED = "MP4 already exists"

LIGHT = {
    "bg": "#f4f4f5",
    "fg": "#18181b",
    "muted": "#737373",
    "field": "#ffffff",
    "tree": "#ffffff",
    "heading": "#f4f4f5",
    "checked": "#f4f4f5",
    "select": "#e5e5e5",
    "log": "#fafafa",
    "border": "#e5e5e5",
    "button": "#ececec",
    "button_hover": "#e5e5e5",
    "accent": "#7c3aed",
    "accent_hover": "#6d28d9",
    "accent_fg": "#ffffff",
}
DARK = {
    "bg": "#171717",
    "fg": "#f5f5f5",
    "muted": "#a3a3a3",
    "field": "#262626",
    "tree": "#1f1f1f",
    "heading": "#262626",
    "checked": "#2a2a2a",
    "select": "#2f2f2f",
    "log": "#141414",
    "border": "#2e2e2e",
    "button": "#2a2a2a",
    "button_hover": "#333333",
    "accent": "#a855f7",
    "accent_hover": "#9333ea",
    "accent_fg": "#ffffff",
}


def load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_config()
    merged.update(data)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")


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
        self.title(APP_NAME)
        self.minsize(920, 600)
        self.geometry("1080x740")
        self.option_add("*Font", FONT)
        self._set_window_icon()

        self.ffmpeg = find_ffmpeg()
        cfg = load_config()
        self.watch_folder = tk.StringVar(value=cfg.get("watch_folder", ""))
        self.output_folder = tk.StringVar(value=cfg.get("output_folder", ""))
        same = cfg.get("same_output", True)
        if not str(cfg.get("output_folder", "")).strip():
            same = True
        self.same_output = tk.BooleanVar(value=same)
        self.recursive = tk.BooleanVar(value=False)
        self.show_log = tk.BooleanVar(value=bool(cfg.get("show_log", True)))
        self.stream_deck_enabled = tk.BooleanVar(value=bool(cfg.get("stream_deck", True)))
        self.dark_mode = tk.BooleanVar(value=bool(cfg.get("dark_mode", False)))
        self.watching = False
        self._settings_win: tk.Toplevel | None = None

        self.baseline: set[str] = set()
        self.file_status: dict[str, str] = {}
        self.size_history: dict[str, list[int]] = {}
        self.queued: set[str] = set()
        self.jobs: queue.Queue[tuple[str, Path, Path]] = queue.Queue()
        self.ui_events: queue.Queue[tuple] = queue.Queue()
        self._api_jobs: queue.Queue[tuple] = queue.Queue()
        self.sort_column = "name"
        self.sort_reverse = False
        self.sort_keys: dict[str, dict[str, object]] = {}
        self.checked: set[str] = set()
        self.deck_api = StreamDeckApi(self)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self._drain_ui_events)
        self._refresh_ffmpeg_label()
        self._apply_theme()
        self._apply_log_visibility()
        self._apply_stream_deck()

        if self.watch_folder.get():
            self.refresh_file_list(initial=True)

    def _set_window_icon(self) -> None:
        png = asset_path("remuxr_logo.png")
        ico = asset_path("remuxr.ico")
        if png.is_file():
            logo = tk.PhotoImage(file=str(png))
            factor = max(1, logo.height() // 32)
            if factor > 1:
                logo = logo.subsample(factor, factor)
            self._logo_window = logo
            self.iconphoto(True, self._logo_window)
        if ico.is_file():
            try:
                self.iconbitmap(str(ico))
            except tk.TclError:
                pass

    def _colors(self) -> dict[str, str]:
        return DARK if self.dark_mode.get() else LIGHT

    def _frame(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=self._colors()["bg"])
        self._shell.append(frame)
        return frame

    def _label(self, parent: tk.Misc, text: str, *, muted: bool = False) -> tk.Label:
        colors = self._colors()
        label = tk.Label(
            parent,
            text=text,
            font=FONT_SMALL if muted else FONT,
            bg=colors["bg"],
            fg=colors["muted"] if muted else colors["fg"],
            anchor="w",
        )
        self._labels.append((label, muted))
        return label

    def _icon_check(
        self,
        parent: tk.Misc,
        text: str,
        variable: tk.BooleanVar,
        command,
    ) -> IconCheck:
        widget = IconCheck(
            parent,
            text=text,
            variable=variable,
            command=command,
            get_icons=lambda: self.icons,
            get_colors=self._colors,
        )
        self._checks.append(widget)
        return widget

    def _build(self) -> None:
        self.icons = IconSet(self, dark=self.dark_mode.get())
        self._shell: list[tk.Frame] = []
        self._labels: list[tuple[tk.Label, bool]] = []
        self._buttons: list[FlatButton] = []
        self._checks: list[IconCheck] = []
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        try:
            self.style.layout(
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

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = self._frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        title_row = self._frame(header)
        title_row.pack(fill="x")
        self._label(title_row, "Watch folder").pack(side="left")
        self.settings_btn = tk.Button(
            title_row,
            image=self.icons.menu,
            command=self.open_settings,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=0,
        )
        self.settings_btn.pack(side="right")

        row = self._frame(header)
        row.pack(fill="x", pady=(6, 0))
        self.watch_entry = Field(row, textvariable=self.watch_folder)
        self.watch_entry.pack(side="left", fill="x", expand=True, ipady=6)
        browse = FlatButton(row, text="Browse…", command=self.browse_folder)
        browse.pack(side="left", padx=(8, 0))
        self._buttons.append(browse)

        self._label(header, "Save MP4s to").pack(anchor="w", pady=(12, 0))
        out_row = self._frame(header)
        out_row.pack(fill="x", pady=(6, 0))
        self.output_entry = Field(out_row, textvariable=self.output_folder)
        self.output_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.output_browse = FlatButton(out_row, text="Browse…", command=self.browse_output_folder)
        self.output_browse.pack(side="left", padx=(8, 0))
        self._buttons.append(self.output_browse)
        self._icon_check(
            header,
            "Save next to the MKV (same folder)",
            self.same_output,
            self._sync_output_controls,
        ).pack(anchor="w", pady=(8, 0))

        controls = self._frame(self)
        controls.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        self.start_btn = FlatButton(controls, text="Start watching", variant="primary", command=self.start_watching)
        self.start_btn.pack(side="left")
        self.stop_btn = FlatButton(controls, text="Stop", command=self.stop_watching, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self._buttons.extend((self.start_btn, self.stop_btn))
        self._icon_check(controls, "Include subfolders", self.recursive, self.on_recursive_toggle).pack(
            side="left", padx=(16, 0)
        )
        self.ffmpeg_label = self._label(controls, "", muted=True)
        self.ffmpeg_label.pack(side="right")
        self.streamdeck_label = self._label(controls, "", muted=True)
        self.streamdeck_label.pack(side="right", padx=(0, 16))

        self.hint = tk.Label(
            self,
            text="Existing .mkv files are listed but never remuxed automatically. "
            "Only files that appear after you start watching are remuxed on their own. "
            "If a shared folder is read-only, save MP4s to a local folder instead.",
            wraplength=980,
            justify="left",
            font=FONT_SMALL,
            anchor="w",
        )
        self.hint.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        self._labels.append((self.hint, True))

        self.list_shell = tk.Frame(self)
        self.list_shell.grid(row=3, column=0, sticky="nsew", padx=20, pady=4)
        tree_frame = tk.Frame(self.list_shell)
        tree_frame.pack(fill="both", expand=True, padx=1, pady=1)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=(*LIST_COLUMNS, "spacer"),
            show="tree headings",
            selectmode="none",
        )
        self.tree.column("#0", width=42, minwidth=42, stretch=False, anchor="center")
        self.tree.column("name", width=280, minwidth=120, stretch=False)
        self.tree.column("status", width=280, minwidth=80, stretch=False)
        self.tree.column("size", width=90, minwidth=50, stretch=False, anchor="e")
        self.tree.column("date", width=140, minwidth=80, stretch=False)
        self.tree.heading("spacer", text="")
        self.tree.column("spacer", width=0, minwidth=0, stretch=True)
        self._refresh_headings()
        self._locked_name_width: int | None = None
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<B1-Motion>", self._on_column_drag)
        self.tree.bind("<ButtonRelease-1>", self._on_column_drag_end)
        yscroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview, style="Modern.Vertical.TScrollbar"
        )
        xscroll = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview, style="Modern.Horizontal.TScrollbar"
        )
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        actions = self._frame(self)
        actions.grid(row=4, column=0, sticky="ew", padx=20, pady=8)
        for text, cmd in (
            ("Remux selected", self.remux_selected),
            ("Select all", lambda: self._set_all_checked(True)),
            ("Clear", lambda: self._set_all_checked(False)),
            ("Refresh list", lambda: self.refresh_file_list()),
            ("Open folder", self.open_folder),
        ):
            btn = FlatButton(actions, text=text, command=cmd)
            btn.pack(side="left", padx=(0, 8))
            self._buttons.append(btn)

        self.log_frame = self._frame(self)
        self.log_label = self._label(self.log_frame, "Log", muted=True)
        self.log_label.pack(anchor="w")
        self.log = tk.Text(
            self.log_frame,
            height=7,
            wrap="word",
            state="disabled",
            relief="flat",
            bd=0,
            highlightthickness=1,
            font=FONT_LOG,
        )
        self.log.pack(fill="both", expand=True, pady=(6, 0))
        self._log_grid = {"row": 5, "column": 0, "sticky": "ew", "padx": 20, "pady": (0, 16)}

        threading.Thread(target=self._worker_loop, daemon=True).start()
        self._sync_output_controls()

    def persist_settings(self) -> None:
        save_config(
            {
                "watch_folder": self.watch_folder.get().strip(),
                "output_folder": self.output_folder.get().strip(),
                "same_output": self.same_output.get(),
                "show_log": self.show_log.get(),
                "stream_deck": self.stream_deck_enabled.get(),
                "dark_mode": self.dark_mode.get(),
            }
        )

    def open_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        colors = self._colors()
        win = tk.Toplevel(self)
        self._settings_win = win
        win.title("Settings")
        win.resizable(False, False)
        win.transient(self)
        win.configure(bg=colors["bg"])
        frame = tk.Frame(win, bg=colors["bg"], padx=22, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Settings", font=FONT, bg=colors["bg"], fg=colors["fg"]).pack(anchor="w", pady=(0, 12))
        for text, var, cmd in (
            ("Show log", self.show_log, self._on_show_log_toggle),
            ("Stream Deck connection", self.stream_deck_enabled, self._on_stream_deck_toggle),
            ("Dark mode", self.dark_mode, self._on_dark_mode_toggle),
        ):
            check = IconCheck(
                frame,
                text=text,
                variable=var,
                command=cmd,
                get_icons=lambda: self.icons,
                get_colors=self._colors,
            )
            check.pack(anchor="w", pady=5)
            self._checks.append(check)
        close = FlatButton(frame, text="Close", command=self._close_settings)
        close.pack(anchor="e", pady=(16, 0))
        close.paint(colors)
        win.protocol("WM_DELETE_WINDOW", self._close_settings)
        win.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - win.winfo_reqwidth() - 28
        y = self.winfo_rooty() + 56
        win.geometry(f"+{x}+{y}")

    def _close_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            for child in self._settings_win.winfo_children():
                self._forget_settings_checks(child)
            self._settings_win.destroy()
        self._settings_win = None

    def _forget_settings_checks(self, widget: tk.Misc) -> None:
        if isinstance(widget, IconCheck) and widget in self._checks:
            self._checks.remove(widget)
        for child in widget.winfo_children():
            self._forget_settings_checks(child)

    def _on_show_log_toggle(self) -> None:
        self._apply_log_visibility()
        self.persist_settings()

    def _on_stream_deck_toggle(self) -> None:
        self._apply_stream_deck()
        self.persist_settings()
        if not self.stream_deck_enabled.get():
            self.log_line("Stream Deck connection turned off.")
        elif self.deck_api.running:
            self.log_line(f"Stream Deck connection turned on (port {DEFAULT_PORT}).")
        else:
            self.log_line("Stream Deck connection could not start: port busy.")

    def _on_dark_mode_toggle(self) -> None:
        self._apply_theme()
        self.persist_settings()

    def _apply_log_visibility(self) -> None:
        if self.show_log.get():
            self.log_frame.grid(**self._log_grid)
        else:
            self.log_frame.grid_remove()

    def _apply_stream_deck(self) -> None:
        if self.stream_deck_enabled.get():
            if not self.deck_api.running:
                self.deck_api.start()
            if self.deck_api.running:
                self.streamdeck_label.configure(text=f"Stream Deck: :{DEFAULT_PORT}")
            else:
                self.streamdeck_label.configure(text="Stream Deck: port busy")
        else:
            self.deck_api.stop()
            self.streamdeck_label.configure(text="Stream Deck: off")

    def _apply_theme(self) -> None:
        colors = self._colors()
        self.icons = IconSet(self, dark=self.dark_mode.get())
        self.configure(bg=colors["bg"])
        self.settings_btn.configure(image=self.icons.menu, bg=colors["bg"], activebackground=colors["button"])
        self.settings_btn.image = self.icons.menu
        for frame in self._shell:
            if frame.winfo_exists():
                frame.configure(bg=colors["bg"])
        if self.list_shell.winfo_exists():
            self.list_shell.configure(bg=colors["border"])
            for child in self.list_shell.winfo_children():
                child.configure(bg=colors["tree"])
        for label, muted in self._labels:
            if label.winfo_exists():
                label.configure(bg=colors["bg"], fg=colors["muted"] if muted else colors["fg"])
        self.watch_entry.paint(colors)
        self.output_entry.paint(colors, enabled=not self.same_output.get())
        for btn in self._buttons:
            if btn.winfo_exists():
                btn.paint(colors)
        for check in list(self._checks):
            if check.winfo_exists():
                check.paint()
            else:
                self._checks.remove(check)
        flatten_tree_style(self.style, colors)
        self.tree.tag_configure("checked", background=colors["checked"])
        self.log.configure(
            bg=colors["log"],
            fg=colors["fg"],
            insertbackground=colors["fg"],
            highlightbackground=colors["border"],
            highlightcolor=colors["border"],
        )
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.configure(bg=colors["bg"])
            self._paint_widget_tree(self._settings_win, colors)
        for iid in self.tree.get_children(""):
            on = iid in self.checked
            self.tree.item(iid, image=self.icons.checked if on else self.icons.unchecked)
        self._refresh_headings()

    def _paint_widget_tree(self, widget: tk.Misc, colors: dict[str, str]) -> None:
        try:
            if isinstance(widget, FlatButton):
                widget.paint(colors)
            elif isinstance(widget, IconCheck):
                widget.paint()
            elif isinstance(widget, (tk.Frame, tk.Label, tk.Toplevel)):
                widget.configure(bg=colors["bg"])
                if isinstance(widget, tk.Label):
                    widget.configure(fg=colors["fg"])
        except tk.TclError:
            return
        for child in widget.winfo_children():
            self._paint_widget_tree(child, colors)

    def _sync_output_controls(self) -> None:
        enabled = not self.same_output.get()
        self.output_entry.configure(state="normal" if enabled else "disabled")
        self.output_browse.configure(state="normal" if enabled else "disabled")
        self.output_entry.paint(self._colors(), enabled=enabled)
        self.output_browse.paint(self._colors())
        self.persist_settings()

    def output_dir_path(self) -> Path | None:
        if self.same_output.get():
            return self.folder_path()
        raw = self.output_folder.get().strip()
        if not raw:
            return self.folder_path()
        return Path(raw)

    def dest_for(self, mkv_path: Path) -> Path:
        return output_path_for(mkv_path, self.output_dir_path(), self.folder_path())

    def _can_write(self, folder: Path) -> bool:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".mkv-to-mp4-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False

    def _writable_output_dir(self, watch_folder: Path) -> Path | None:
        dest = self.output_dir_path() or watch_folder
        if dest and self._can_write(dest):
            return dest
        for candidate in (
            Path.home() / "Videos" / "MKV to MP4",
            APP_DIR / "output",
        ):
            if self._can_write(candidate):
                self.same_output.set(False)
                self.output_folder.set(str(candidate))
                self._sync_output_controls()
                self.log_line(f"Cannot write to {dest}. Saving MP4s to {candidate}")
                return candidate
        return None

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
        if region == "separator":
            column = self.tree.identify_column(event.x)
            # #1 is File; dragging that edge should change File. Other edges should not.
            if column in {"#2", "#3", "#4", "#5"}:
                self._locked_name_width = int(self.tree.column("name", "width"))
            else:
                self._locked_name_width = None
            return None
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

    def _on_column_drag(self, _event: tk.Event) -> None:
        if self._locked_name_width is not None:
            self.tree.column("name", width=self._locked_name_width)

    def _on_column_drag_end(self, _event: tk.Event) -> None:
        if self._locked_name_width is not None:
            self.tree.column("name", width=self._locked_name_width)
        self._locked_name_width = None

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
        self.persist_settings()
        if self.watching:
            self.stop_watching()
        self.refresh_file_list(initial=True)

    def browse_output_folder(self) -> None:
        initial = self.output_folder.get() or self.watch_folder.get() or str(Path.home())
        chosen = filedialog.askdirectory(title="Choose a folder for MP4 files", initialdir=initial)
        if not chosen:
            return
        self.output_folder.set(chosen)
        self.persist_settings()

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
            if status == STATUS_EXISTING and self.dest_for(path).is_file():
                status = f"{STATUS_EXISTING} · {STATUS_SKIPPED}"
            self._put_row(path, status, apply_sort=False)
        self._apply_sort()
        self._refresh_headings()

    def call_on_ui(self, fn) -> str | None:  # noqa: ANN001
        box: dict[str, str | None] = {}
        done = threading.Event()
        self._api_jobs.put((fn, box, done))
        if not done.wait(20):
            return "The app did not respond."
        return box.get("error")

    def stream_deck_status(self) -> dict:
        return {
            "ok": True,
            "watching": self.watching,
            "folder": self.watch_folder.get().strip(),
        }

    def api_start_watching(self) -> str | None:
        error = self.start_watching(interactive=False)
        if error:
            self.log_line(f"Stream Deck could not start watching: {error}")
        else:
            self.log_line("Stream Deck started watching.")
        return error

    def api_stop_watching(self) -> str | None:
        if self.watching:
            self.stop_watching()
            self.log_line("Stream Deck stopped watching.")
        return None

    def api_toggle_watching(self) -> str | None:
        if self.watching:
            return self.api_stop_watching()
        return self.api_start_watching()

    def start_watching(self, interactive: bool = True) -> str | None:
        if self.watching:
            return None
        folder = self.folder_path()
        if not folder or not folder.is_dir():
            msg = "Choose an existing folder to watch."
            if interactive:
                messagebox.showerror("Folder needed", msg)
            return msg
        if not self.ffmpeg:
            self.ffmpeg = find_ffmpeg()
            self._refresh_ffmpeg_label()
        if not self.ffmpeg:
            msg = "FFmpeg was not found."
            if interactive:
                messagebox.showerror(
                    "FFmpeg not found",
                    "Install FFmpeg and make sure it is on your PATH, then try again.",
                )
            return msg

        out_dir = self._writable_output_dir(folder)
        if out_dir is None:
            msg = "Cannot write MP4s (share is read-only and no local folder worked)."
            if interactive:
                messagebox.showerror("Cannot write here", msg)
            return msg

        self.persist_settings()
        existing = list_mkv_files(folder, self.recursive.get())
        self.baseline = {str(p) for p in existing}
        self.file_status = {str(p): STATUS_EXISTING for p in existing}
        self.size_history.clear()
        self.queued.clear()
        self.watching = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.start_btn.paint(self._colors())
        self.stop_btn.paint(self._colors())
        self.refresh_file_list()
        self.log_line(f"Watching {folder}")
        dest = self.output_dir_path()
        if dest and dest != folder:
            self.log_line(f"Saving MP4s to {dest}")
        self.log_line(
            f"Found {len(existing)} existing .mkv file(s). They will not be remuxed unless you select them."
        )
        threading.Thread(target=self._watch_loop, daemon=True).start()
        return None

    def stop_watching(self) -> None:
        if not self.watching:
            return
        self.watching = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.start_btn.paint(self._colors())
        self.stop_btn.paint(self._colors())
        self.log_line("Stopped watching.")

    def open_folder(self) -> None:
        target = self.output_dir_path() or self.folder_path()
        if target and target.is_dir():
            os.startfile(target)  # type: ignore[attr-defined]
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
        self.jobs.put((reason, path, self.dest_for(path)))
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
                    if self.dest_for(path).is_file():
                        self.file_status[key] = STATUS_SKIPPED
                        self.ui_events.put(("upsert", path, STATUS_SKIPPED))
                        self.ui_events.put(("log", f"Skipped (MP4 exists): {path.name}"))
                        continue
                    self.ui_events.put(("enqueue_auto", path))
            time.sleep(POLL_SECONDS)

    def _worker_loop(self) -> None:
        while True:
            reason, path, dest = self.jobs.get()
            try:
                remux_mkv_to_mp4(path, self.ffmpeg, dest)
                self.ui_events.put(("done", path, reason, dest))
            except Exception as exc:  # noqa: BLE001 — show any remux failure in the UI
                self.ui_events.put(("failed", path, str(exc)))
            finally:
                self.jobs.task_done()

    def _drain_ui_events(self) -> None:
        while True:
            try:
                fn, box, done = self._api_jobs.get_nowait()
            except queue.Empty:
                break
            try:
                box["error"] = fn()
            except Exception as exc:  # noqa: BLE001
                box["error"] = str(exc)
            done.set()
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
                path, reason, dest = event[1], event[2], event[3]
                key = str(path)
                self.queued.discard(key)
                self.file_status[key] = STATUS_DONE
                self._set_row_status(path, STATUS_DONE)
                self.log_line(f"Finished ({reason}): {dest}")
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
        self.persist_settings()
        if self.deck_api:
            self.deck_api.stop()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
