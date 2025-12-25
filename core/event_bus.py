from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, DefaultDict, List, Optional
from collections import defaultdict

from core.event_types import EventType, as_event_type


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: Any = None
    ts: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=lambda: threading.get_ident())


Handler = Callable[[Event], None]


class EventBus:
    """
    Strict typed-payload EventBus.

    Rules:
    - publish(): payload must NOT be dict; validated against registry
    - post_payload(): the only public send API (besides publish)
    - NO post(**kwargs) builder (project is fully typed now)
    """

    def __init__(self) -> None:
        self._q: "queue.Queue[Event]" = queue.Queue()
        self._handlers: DefaultDict[EventType, List[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    # ---------- publish side (thread-safe) ----------

    def publish(self, event: Event) -> None:
        if not isinstance(event, Event):
            raise TypeError("publish() expects an Event")
        if isinstance(event.payload, dict):
            raise TypeError(f"dict payload is not allowed for {event.type.value}")

        # registry validation (exact payload class check)
        from core.events.registry import validate_payload
        validate_payload(event.type, event.payload)

        self._q.put(event)

    def post_payload(self, event_type: EventType | str, payload: Any = None) -> None:
        et = as_event_type(event_type)
        if isinstance(payload, dict):
            raise TypeError(f"dict payload is not allowed for {et.value}")
        self.publish(Event(type=et, payload=payload))

    # ---------- subscribe side ----------

    def subscribe(self, event_type: EventType | str, handler: Handler) -> None:
        et = as_event_type(event_type)
        if handler is None:
            raise ValueError("handler cannot be None")
        with self._lock:
            self._handlers[et].append(handler)

    def unsubscribe(self, event_type: EventType | str, handler: Handler) -> None:
        et = as_event_type(event_type)
        with self._lock:
            if et not in self._handlers:
                return
            self._handlers[et] = [h for h in self._handlers[et] if h is not handler]

    # ---------- dispatch side (call from UI thread) ----------

    def dispatch_pending(
        self,
        *,
        max_events: int = 200,
        on_error: Optional[Callable[[Event, BaseException], None]] = None,
    ) -> int:
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
            finally:
                self._q.task_done()

            dispatched += 1

        return dispatched

    def _dispatch_one(self, ev: Event) -> None:
        with self._lock:
            specific = list(self._handlers.get(ev.type, []))
            wildcard = list(self._handlers.get(EventType.ANY, []))

        for h in specific:
            h(ev)
        for h in wildcard:
            h(ev)

    def pending_count_approx(self) -> int:
        try:
            return int(self._q.qsize())
        except Exception:
            return 0