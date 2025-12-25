from __future__ import annotations

import tkinter as tk

from core.models.app_state import AppState
from core.repos.app_state_repo import AppStateRepo


class WindowStateController:
    def __init__(self, *, root: tk.Misc, repo: AppStateRepo, state: AppState) -> None:
        self._root = root
        self._repo = repo
        self._state = state

    def apply_initial_geometry(self) -> None:
        w = int(getattr(self._state.window, "width", 1100) or 1100)
        h = int(getattr(self._state.window, "height", 720) or 720)
        x = getattr(self._state.window, "x", None)
        y = getattr(self._state.window, "y", None)
        try:
            if isinstance(x, int) and isinstance(y, int):
                self._root.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self._root.geometry(f"{w}x{h}")
        except Exception:
            pass

    def persist_current_geometry(self) -> None:
        try:
            self._root.update_idletasks()
            self._state.window.width = int(self._root.winfo_width())
            self._state.window.height = int(self._root.winfo_height())
            self._state.window.x = int(self._root.winfo_x())
            self._state.window.y = int(self._root.winfo_y())
            self._repo.save(self._state)
        except Exception:
            pass