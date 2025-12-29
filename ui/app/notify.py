# File: ui/app/notify.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ui.app.status import StatusController


@dataclass
class UiNotify:
    """
    Thread-safe UI notifier.
    Can be called from ANY thread. Internally marshals to UI thread via call_soon().
    """
    call_soon: Callable[[Callable[[], None]], None]
    status: StatusController

    def info(self, msg: str) -> None:
        s = (msg or "").strip()
        if not s:
            return
        try:
            self.call_soon(lambda: self.status.info(s))
        except Exception:
            pass

    def status_msg(self, msg: str, *, ttl_ms: Optional[int] = 2000) -> None:
        s = (msg or "").strip()
        if not s:
            return
        try:
            self.call_soon(lambda: self.status.status_msg(s, ttl_ms=ttl_ms))
        except Exception:
            pass

    def error(self, msg: str, *, detail: str = "") -> None:
        s = (msg or "").strip()
        if not s:
            return
        d = (detail or "").strip()
        try:
            self.call_soon(lambda: self.status.error(s, detail=d))
        except Exception:
            pass

    def apply_theme(self, theme: str) -> None:
        t = (theme or "").strip()
        if not t:
            return
        try:
            self.call_soon(lambda: self.status.apply_theme(t))
        except Exception:
            pass