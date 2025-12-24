from __future__ import annotations

import sys
import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import RIGHT, LEFT, Y, BOTH


class ScrollableFrame(tb.Frame):
    """
    A simple, version-independent scrollable frame:
    - Canvas + vertical scrollbar
    - inner: the content frame you should pack/grid widgets into
    """

    def __init__(self, master: tk.Misc, *, padding=0, bootstyle: str = "round") -> None:
        super().__init__(master, padding=padding)

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._vsb = tb.Scrollbar(self, orient="vertical", command=self._canvas.yview, bootstyle=bootstyle)
        self._canvas.configure(yscrollcommand=self._vsb.set)

        self._vsb.pack(side=RIGHT, fill=Y)
        self._canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.inner = tb.Frame(self._canvas)
        self._window_id = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel support (Windows/macOS/Linux)
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _evt=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, evt) -> None:
        # Keep inner frame width same as canvas width
        self._canvas.itemconfigure(self._window_id, width=evt.width)

    def _bind_mousewheel(self, _evt=None) -> None:
        if sys.platform.startswith("win") or sys.platform == "darwin":
            self._canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        else:
            # Linux (X11)
            self._canvas.bind_all("<Button-4>", self._on_mousewheel_linux, add="+")
            self._canvas.bind_all("<Button-5>", self._on_mousewheel_linux, add="+")

    def _unbind_mousewheel(self, _evt=None) -> None:
        if sys.platform.startswith("win") or sys.platform == "darwin":
            self._canvas.unbind_all("<MouseWheel>")
        else:
            self._canvas.unbind_all("<Button-4>")
            self._canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, evt) -> None:
        # Windows: evt.delta is multiple of 120; macOS may differ
        delta = evt.delta
        if sys.platform == "darwin":
            # macOS delta is already small; invert to natural feel if needed
            self._canvas.yview_scroll(int(-1 * delta), "units")
        else:
            self._canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _on_mousewheel_linux(self, evt) -> None:
        if evt.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif evt.num == 5:
            self._canvas.yview_scroll(1, "units")