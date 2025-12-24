from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb

from ui.widgets.color_swatch import ColorSwatch


class PickPreviewWindow(tk.Toplevel):
    """
    Borderless topmost preview window.
    Behavior:
    - Starts hidden (withdraw)
    - AppWindow decides when to show/move/update it
    - Clicking it will generate a virtual event on master to cancel picking
    """

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        # No window decorations
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-toolwindow", True)
        except Exception:
            pass

        # Hide initially to avoid stuck box at (0,0)
        self.withdraw()

        self._w = 180
        self._h = 74

        self._frame = tb.Frame(self, padding=8)
        self._frame.pack(fill="both", expand=True)

        self._var_xy = tk.StringVar(value="x=0  y=0")
        tb.Label(self._frame, textvariable=self._var_xy).pack(anchor="w")

        self._swatch = ColorSwatch(self._frame, width=84, height=22)
        self._swatch.pack(anchor="w", pady=(6, 0))

        # initial off-screen position
        self.geometry(f"{self._w}x{self._h}+{-9999}+{-9999}")

        # Click to cancel pick (safety UX)
        def _cancel(_evt=None) -> None:
            try:
                # send to master in UI thread
                master.event_generate("<<PICK_PREVIEW_CANCEL>>", when="tail")
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

    def move_near_cursor(self, *, x: int, y: int, offset: tuple[int, int], anchor: str) -> None:
        ox, oy = offset
        w, h = self._w, self._h

        if anchor == "bottom_right":
            nx, ny = x + ox, y + oy
        elif anchor == "bottom_left":
            nx, ny = x - ox - w, y + oy
        elif anchor == "top_right":
            nx, ny = x + ox, y - oy - h
        elif anchor == "top_left":
            nx, ny = x - ox - w, y - oy - h
        else:
            nx, ny = x + ox, y + oy

        self.move_to(nx, ny)