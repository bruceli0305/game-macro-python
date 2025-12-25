from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable, Optional

from core.event_bus import EventBus, Event

log = logging.getLogger(__name__)


class EventPump:
    """
    Periodically drains EventBus in Tk main thread via after().

    Logging:
    - Any handler exception will be logged with stacktrace (unless caller overrides on_handler_error).
    - Any unexpected pump exception will be logged too.
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
                log.exception("EventPump.after_cancel failed")
            self._after_id = None

    def _schedule(self) -> None:
        if not self._running:
            return
        self._after_id = self._root.after(self._tick_ms, self._tick)

    def _on_error_default(self, ev: Event, err: BaseException) -> None:
        try:
            log.exception("Event handler failed: %s", getattr(ev.type, "value", ev.type), exc_info=err)
        except Exception:
            # last resort: do not crash the UI pump
            pass

    def _tick(self) -> None:
        try:
            on_err = self._on_handler_error or self._on_error_default
            self._bus.dispatch_pending(max_events=200, on_error=on_err)
        except Exception:
            log.exception("EventPump tick failed")
        finally:
            self._schedule()