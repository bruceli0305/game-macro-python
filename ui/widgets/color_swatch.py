from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import LEFT, X


class ColorSwatch(tb.Frame):
    """
    Simple color preview widget using Canvas (theme-independent).
    """

    def __init__(self, master: tk.Misc, *, width: int = 64, height: int = 24) -> None:
        super().__init__(master)

        self._canvas = tk.Canvas(self, width=width, height=height, highlightthickness=0, bd=0)
        self._canvas.pack(side=LEFT)

        self._rect = self._canvas.create_rectangle(0, 0, width, height, outline="")

        self._var = tk.StringVar(value="#000000")
        self._label = tb.Label(self, textvariable=self._var, width=9)
        self._label.pack(side=LEFT, padx=8, fill=X, expand=False)

        self.set_rgb(0, 0, 0)

    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        return f"#{r:02X}{g:02X}{b:02X}"

    def set_rgb(self, r: int, g: int, b: int) -> None:
        hx = self._rgb_to_hex(r, g, b)
        self._canvas.itemconfigure(self._rect, fill=hx)
        self._var.set(hx)

    def set_hex(self, hx: str) -> None:
        s = (hx or "").strip()
        if not s.startswith("#"):
            s = "#" + s
        if len(s) != 7:
            return
        self._canvas.itemconfigure(self._rect, fill=s)
        self._var.set(s.upper())

    def get_hex(self) -> str:
        return self._var.get()