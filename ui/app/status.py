from __future__ import annotations

import tkinter as tk
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import LEFT, X, Y, VERTICAL

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.payloads import InfoPayload, StatusPayload, ErrorPayload, ThemeChangePayload

try:
    from ttkbootstrap.toast import ToastNotification  # type: ignore
except Exception:
    ToastNotification = None


class StatusBar(tb.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(10, 6))
        self._profile_var = tk.StringVar(value="profile: -")
        self._page_var = tk.StringVar(value="page: -")
        self._status_var = tk.StringVar(value="ready")

        tb.Label(self, textvariable=self._profile_var).pack(side=LEFT)
        tb.Separator(self, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)
        tb.Label(self, textvariable=self._page_var).pack(side=LEFT)
        tb.Separator(self, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)
        tb.Label(self, textvariable=self._status_var, anchor="w").pack(side=LEFT, fill=X, expand=True)

    def set_profile(self, name: str) -> None:
        self._profile_var.set(f"profile: {name}")

    def set_page(self, name: str) -> None:
        self._page_var.set(f"page: {name}")

    def set_status(self, text: str) -> None:
        self._status_var.set(text)


class StatusController:
    """
    Owns status bar + toast + theme apply.
    Strict typed payload version (no dict compatibility).
    """

    def __init__(self, *, root: tb.Window, bar: StatusBar, bus: EventBus) -> None:
        self._root = root
        self._bar = bar
        self._bus = bus
        self._status_after_id: str | None = None
        self._toast_available = ToastNotification is not None

        self._bus.subscribe(EventType.UI_THEME_CHANGE, self._on_theme_change)
        self._bus.subscribe(EventType.INFO, self._on_info)
        self._bus.subscribe(EventType.ERROR, self._on_error)
        self._bus.subscribe(EventType.STATUS, self._on_status)

    def set_profile(self, name: str) -> None:
        self._bar.set_profile(name)

    def set_page(self, name: str) -> None:
        self._bar.set_page(name)

    def set_status(self, text: str, *, ttl_ms: Optional[int] = None) -> None:
        self._bar.set_status(text)

        if self._status_after_id is not None:
            try:
                self._root.after_cancel(self._status_after_id)
            except Exception:
                pass
            self._status_after_id = None

        if ttl_ms is not None and ttl_ms > 0:
            self._status_after_id = self._root.after(ttl_ms, lambda: self._bar.set_status("ready"))

    def _toast(self, title: str, message: str, bootstyle: str) -> None:
        if not self._toast_available:
            return
        try:
            ToastNotification(  # type: ignore[misc]
                title=title,
                message=message,
                duration=2500,
                bootstyle=bootstyle,
            ).show_toast()
        except Exception:
            pass

    def _on_theme_change(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, ThemeChangePayload):
            return
        theme = (p.theme or "").strip()
        if not theme:
            return
        try:
            self._root.style.theme_use(theme)  # ttkbootstrap Window has .style
            self.set_status(f"INFO: theme -> {theme}", ttl_ms=2500)
        except Exception as e:
            self.set_status(f"ERROR: theme apply failed: {e}", ttl_ms=6000)
            self._toast("ERROR", f"theme apply failed: {e}", "danger")

    def _on_info(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, InfoPayload):
            return
        msg = (p.msg or "").strip()
        if not msg:
            return
        self.set_status(f"INFO: {msg}", ttl_ms=3000)
        self._toast("INFO", msg, "success")

    def _on_error(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, ErrorPayload):
            return
        msg = (p.msg or "").strip()
        if not msg:
            return
        self.set_status(f"ERROR: {msg}", ttl_ms=6000)
        self._toast("ERROR", msg, "danger")

    def _on_status(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, StatusPayload):
            return
        msg = (p.msg or "").strip()
        if not msg:
            return
        self.set_status(msg, ttl_ms=2000)