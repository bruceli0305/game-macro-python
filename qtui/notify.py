# qtui/notify.py
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QApplication

from qtui.dispatcher import QtDispatcher
from qtui.status_bar import StatusController
from qtui.theme import apply_theme as apply_theme_fn


@dataclass
class UiNotify:
    """
    线程安全 UI 通知：
    - info / error / status_msg：通过 StatusController 显示到状态栏
    - apply_theme：根据 theme 名称应用 Qt 主题
    - 所有方法都可以在任意线程调用，内部用 QtDispatcher 切回 UI 线程
    """
    dispatcher: QtDispatcher
    status: StatusController

    def info(self, msg: str, ttl_ms: int = 3000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        self.dispatcher.call_soon(lambda: self.status.info(s, ttl_ms=ttl_ms))

    def status_msg(self, msg: str, *, ttl_ms: int = 2000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        self.dispatcher.call_soon(lambda: self.status.status_msg(s, ttl_ms=ttl_ms))

    def error(self, msg: str, *, detail: str = "", ttl_ms: int = 6000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        d = (detail or "").strip()
        text = s if not d else f"{s}：{d}"
        self.dispatcher.call_soon(lambda: self.status.error(text, ttl_ms=ttl_ms))

    def apply_theme(self, theme: str) -> None:
        """
        在线程安全地应用 Qt 主题（暗/亮）。
        """
        t = (theme or "").strip()
        if not t:
            return

        app = QApplication.instance()
        if app is None:
            return

        def _do():
            apply_theme_fn(app, t)

        self.dispatcher.call_soon(_do)