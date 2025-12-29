# File: ui/runtime/ui_dispatcher.py
from __future__ import annotations

import queue
import tkinter as tk
from typing import Callable, Optional


class UiDispatcher:
    """
    UI-thread task dispatcher:
    - background threads call: dispatcher.call_soon(fn)
    - UI thread drains tasks via Tk.after tick
    """

    def __init__(self, *, root: tk.Misc, tick_ms: int = 8, max_tasks_per_tick: int = 200) -> None:
        self._root = root
        self._tick_ms = int(max(1, tick_ms))
        self._max = int(max(1, max_tasks_per_tick))

        self._q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._running = False
        self._after_id: Optional[str] = None

    def call_soon(self, fn: Callable[[], None]) -> None:
        if fn is None:
            return
        self._q.put(fn)

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
            for _ in range(self._max):
                try:
                    fn = self._q.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                finally:
                    try:
                        self._q.task_done()
                    except Exception:
                        pass
        finally:
            self._schedule()