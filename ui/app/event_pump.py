from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from core.event_bus import EventBus, Event


class EventPump:
    """
    Periodically drains EventBus in Tk main thread via after().
    """

    def __init__(
        self,
        *,
        root: tk.Misc,
        bus: EventBus,
        tick_ms: int = 16,
        on_handler_error: Optional[Callable[[Event, BaseException], None]] = None,
    ) -> None:
        self._root = root
        self._bus = bus
        self._tick_ms = int(max(5, tick_ms))
        self._on_handler_error = on_handler_error
        self._after_id: str | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _schedule(self) -> None:
        if not self._running:
            return
        self._after_id = self._root.after(self._tick_ms, self._tick)

    def _tick(self) -> None:
        try:
            self._bus.dispatch_pending(max_events=200, on_error=self._on_handler_error)
        finally:
            self._schedule()