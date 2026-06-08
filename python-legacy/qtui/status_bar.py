# qtui/status_bar.py
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMainWindow, QStatusBar, QLabel
from PySide6.QtCore import QTimer


class StatusController:
    """
    封装 QStatusBar：
    - 左侧：profile、page
    - 右侧：当前状态文本（支持 TTL 自动恢复为 "ready"）
    """

    def __init__(self, main_window: QMainWindow) -> None:
        self._bar: QStatusBar = main_window.statusBar()

        self._lbl_profile = QLabel("profile: -")
        self._lbl_page = QLabel("page: -")
        self._lbl_status = QLabel("ready")

        self._bar.addWidget(self._lbl_profile)
        self._bar.addWidget(self._lbl_page)
        self._bar.addPermanentWidget(self._lbl_status, 1)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reset_status)

    # --- 基本 set 方法 ---
    def set_profile(self, name: str) -> None:
        self._lbl_profile.setText(f"profile: {name}")

    def set_page(self, name: str) -> None:
        self._lbl_page.setText(f"page: {name}")

    def set_status(self, text: str, *, ttl_ms: Optional[int] = None) -> None:
        self._lbl_status.setText(text)
        self._timer.stop()
        if ttl_ms is not None and ttl_ms > 0:
            self._timer.start(ttl_ms)

    # --- 供 UiNotify 等复用的便捷方法 ---
    def info(self, msg: str, ttl_ms: int = 3000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        self.set_status(f"INFO: {s}", ttl_ms=ttl_ms)

    def error(self, msg: str, ttl_ms: int = 6000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        self.set_status(f"ERROR: {s}", ttl_ms=ttl_ms)

    def status_msg(self, msg: str, ttl_ms: int = 2000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        self.set_status(s, ttl_ms=ttl_ms)

    # --- 内部 ---
    def _reset_status(self) -> None:
        self._lbl_status.setText("ready")