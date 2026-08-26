"""Flat tk widgets so the app does not inherit Windows 3-D chrome."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_HEAD = ("Segoe UI", 10, "bold")
FONT_LOG = ("Consolas", 9)


class FlatButton(tk.Button):
    def __init__(
        self,
        master: tk.Misc,
        *,
        variant: str = "secondary",
        **kw: object,
    ) -> None:
        self.variant = variant
        super().__init__(
            master,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=FONT,
            padx=14,
            pady=7,
            **kw,  # type: ignore[arg-type]
        )

    def paint(self, colors: dict[str, str]) -> None:
        disabled = str(self["state"]) == "disabled"
        if self.variant == "primary" and not disabled:
            bg, fg, hover = colors["accent"], colors["accent_fg"], colors["accent_hover"]
        else:
            bg, fg, hover = colors["button"], colors["fg"], colors["button_hover"]
            if disabled:
                fg = colors["muted"]
        self.configure(
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            disabledforeground=colors["muted"],
        )


class Field(tk.Entry):
    def __init__(self, master: tk.Misc, **kw: object) -> None:
        super().__init__(
            master,
            relief="flat",
            bd=0,
            highlightthickness=1,
            font=FONT,
            insertwidth=1,
            **kw,  # type: ignore[arg-type]
        )

    def paint(self, colors: dict[str, str], *, enabled: bool = True) -> None:
        bg = colors["field"] if enabled else colors["heading"]
        fg = colors["fg"] if enabled else colors["muted"]
        self.configure(
            bg=bg,
            fg=fg,
            insertbackground=colors["fg"],
            disabledbackground=colors["heading"],
            disabledforeground=colors["muted"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
        )


class IconCheck(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        text: str,
        variable: tk.BooleanVar,
        command: Callable[[], None] | None = None,
        get_icons: Callable,
        get_colors: Callable[[], dict[str, str]],
    ) -> None:
        super().__init__(master)
        self.variable = variable
        self._command = command
        self._get_icons = get_icons
        self._get_colors = get_colors
        self._icon = tk.Label(self, cursor="hand2")
        self._icon.pack(side="left")
        self._label = tk.Label(self, text=text, font=FONT, cursor="hand2", anchor="w")
        self._label.pack(side="left", padx=(8, 0))
        for widget in (self, self._icon, self._label):
            widget.bind("<Button-1>", self._toggle)
        self.paint()

    def _toggle(self, _event: tk.Event | None = None) -> None:
        self.variable.set(not self.variable.get())
        self.paint()
        if self._command:
            self._command()

    def paint(self) -> None:
        colors = self._get_colors()
        icons = self._get_icons()
        img = icons.checked if self.variable.get() else icons.unchecked
        self.configure(bg=colors["bg"])
        self._icon.configure(image=img, bg=colors["bg"])
        self._icon.image = img
        self._label.configure(bg=colors["bg"], fg=colors["fg"])


def flatten_tree_style(style: ttk.Style, colors: dict[str, str]) -> None:
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure(
        "Treeview",
        background=colors["tree"],
        fieldbackground=colors["tree"],
        foreground=colors["fg"],
        bordercolor=colors["tree"],
        lightcolor=colors["tree"],
        darkcolor=colors["tree"],
        borderwidth=0,
        relief="flat",
        rowheight=36,
        indent=0,
        font=FONT,
    )
    style.configure(
        "Treeview.Heading",
        background=colors["heading"],
        foreground=colors["muted"],
        bordercolor=colors["heading"],
        lightcolor=colors["heading"],
        darkcolor=colors["heading"],
        borderwidth=0,
        relief="flat",
        padding=(10, 8),
        font=FONT_HEAD,
    )
    style.map(
        "Treeview",
        background=[("selected", colors["tree"])],
        foreground=[("selected", colors["fg"])],
    )
    style.map("Treeview.Heading", background=[("active", colors["button_hover"])])
    style.configure(
        "Modern.Vertical.TScrollbar",
        gripcount=0,
        background=colors["button"],
        darkcolor=colors["button"],
        lightcolor=colors["button"],
        troughcolor=colors["bg"],
        bordercolor=colors["bg"],
        arrowcolor=colors["muted"],
        relief="flat",
        borderwidth=0,
        arrowsize=12,
        width=10,
    )
    style.configure(
        "Modern.Horizontal.TScrollbar",
        gripcount=0,
        background=colors["button"],
        darkcolor=colors["button"],
        lightcolor=colors["button"],
        troughcolor=colors["bg"],
        bordercolor=colors["bg"],
        arrowcolor=colors["muted"],
        relief="flat",
        borderwidth=0,
        arrowsize=12,
        width=10,
    )
    style.map(
        "Modern.Vertical.TScrollbar",
        background=[("active", colors["muted"]), ("pressed", colors["muted"])],
    )
    style.map(
        "Modern.Horizontal.TScrollbar",
        background=[("active", colors["muted"]), ("pressed", colors["muted"])],
    )
