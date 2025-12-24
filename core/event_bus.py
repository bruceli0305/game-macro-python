from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, DefaultDict, Dict, List, Optional
from collections import defaultdict


@dataclass(frozen=True)
class Event:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=lambda: threading.get_ident())


Handler = Callable[[Event], None]


class EventBus:
    """
    Thread-safe event bus:
    - publish() can be called from ANY thread
    - dispatch_pending() should be called from Tk main thread (or any single UI thread)
    """

    def __init__(self) -> None:
        self._q: "queue.Queue[Event]" = queue.Queue()
        self._handlers: DefaultDict[str, List[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    # ---------- publish side (thread-safe) ----------

    def publish(self, event: Event) -> None:
        """Publish an Event (thread-safe)."""
        if not isinstance(event, Event):
            raise TypeError("publish() expects an Event")
        self._q.put(event)

    def post(self, event_type: str, **payload: Any) -> None:
        """Convenience: create + publish."""
        self.publish(Event(type=event_type, payload=dict(payload)))

    # ---------- subscribe side ----------

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """
        Subscribe handler to an event type.
        event_type="*" means receive all events.
        """
        if not event_type:
            raise ValueError("event_type cannot be empty")
        if handler is None:
            raise ValueError("handler cannot be None")

        with self._lock:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            if event_type not in self._handlers:
                return
            lst = self._handlers[event_type]
            self._handlers[event_type] = [h for h in lst if h is not handler]

    # ---------- dispatch side (call from UI thread) ----------

    def dispatch_pending(
        self,
        *,
        max_events: int = 200,
        on_error: Optional[Callable[[Event, BaseException], None]] = None,
    ) -> int:
        """
        Drain up to max_events events without blocking and dispatch to handlers.
        Returns number of dispatched events.
        """
        dispatched = 0

        while dispatched < max_events:
            try:
                ev = self._q.get_nowait()
            except queue.Empty:
                break

            try:
                self._dispatch_one(ev)
            except BaseException as e:
                if on_error is not None:
                    on_error(ev, e)
                # swallow to keep UI loop alive
            finally:
                self._q.task_done()

            dispatched += 1

        return dispatched

    def _dispatch_one(self, ev: Event) -> None:
        with self._lock:
            specific = list(self._handlers.get(ev.type, []))
            wildcard = list(self._handlers.get("*", []))

        # 先 specific，再 wildcard（可按你喜好调整）
        for h in specific:
            h(ev)
        for h in wildcard:
            h(ev)

    def pending_count_approx(self) -> int:
        """Approximate queue size (Queue.qsize is not reliable across threads, but good for UI hints)."""
        try:
            return int(self._q.qsize())
        except Exception:
            return 0