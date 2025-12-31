# qtui/window_state.py
from __future__ import annotations

import logging

from PySide6.QtWidgets import QMainWindow

from core.models.app_state import AppState
from core.repos.app_state_repo import AppStateRepo

log = logging.getLogger(__name__)


class WindowStateController:
    """
    负责窗口几何状态的恢复/保存：
    - apply_initial_geometry: 从 AppState.window 恢复大小和位置
    - persist_current_geometry: 将当前几何写回 AppState 并保存
    """

    def __init__(self, *, root: QMainWindow, repo: AppStateRepo, state: AppState) -> None:
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
                self._root.resize(w, h)
                self._root.move(x, y)
            else:
                self._root.resize(w, h)
        except Exception:
            log.exception("apply_initial_geometry failed")

    def persist_current_geometry(self) -> None:
        try:
            g = self._root.geometry()
            self._state.window.width = int(g.width())
            self._state.window.height = int(g.height())
            self._state.window.x = int(g.x())
            self._state.window.y = int(g.y())
            self._repo.save(self._state)
        except Exception:
            log.exception("persist_current_geometry failed")