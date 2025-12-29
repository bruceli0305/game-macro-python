# File: ui/pick_preview_window.py
from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb

from ui.widgets.color_swatch import ColorSwatch


class PickPreviewWindow(tk.Toplevel):
    """
    Borderless topmost preview window.
    Clicking it cancels picking via provided callback.
    """

    def __init__(self, master: tk.Misc, *, on_cancel) -> None:
        super().__init__(master)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-toolwindow", True)
        except Exception:
            pass

        self.withdraw()

        self._w = 180
        self._h = 74

        self._frame = tb.Frame(self, padding=8)
        self._frame.pack(fill="both", expand=True)

        self._var_xy = tk.StringVar(value="x=0  y=0")
        tb.Label(self._frame, textvariable=self._var_xy).pack(anchor="w")

        self._swatch = ColorSwatch(self._frame, width=84, height=22)
        self._swatch.pack(anchor="w", pady=(6, 0))

        self.geometry(f"{self._w}x{self._h}+{-9999}+{-9999}")

        def _cancel(_evt=None) -> None:
            try:
                on_cancel()
            except Exception:
                pass

        self.bind("<Button-1>", _cancel)
        self.bind("<Button-3>", _cancel)
        self._frame.bind("<Button-1>", _cancel)
        self._frame.bind("<Button-3>", _cancel)

    @property
    def size(self) -> tuple[int, int]:
        return self._w, self._h

    def show(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.update_idletasks()
        except Exception:
            pass

    def hide(self) -> None:
        try:
            self.withdraw()
        except Exception:
            pass

    def update_preview(self, *, x: int, y: int, r: int, g: int, b: int) -> None:
        self._var_xy.set(f"x={int(x)}  y={int(y)}")
        self._swatch.set_rgb(int(r), int(g), int(b))

    def move_to(self, x: int, y: int) -> None:
        self.geometry(f"{self._w}x{self._h}+{int(x)}+{int(y)}")