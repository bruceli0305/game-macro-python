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
    payload: Any = None  # MUST NOT be dict
    ts: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=lambda: threading.get_ident())


Handler = Callable[[Event], None]


class EventBus:
    """
    Strict typed-payload EventBus.

    Rules:
    - Event.payload must NOT be a dict (runtime enforced).
    - post(event_type, **kwargs) is allowed, BUT it immediately converts kwargs
      into a typed payload dataclass for known event types.
    - post_payload(event_type, payload) accepts typed payload only.
    """

    def __init__(self) -> None:
        self._q: "queue.Queue[Event]" = queue.Queue()
        self._handlers: DefaultDict[EventType, List[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    # ---------- publish side ----------
    def publish(self, event: Event) -> None:
        if not isinstance(event, Event):
            raise TypeError("publish() expects an Event")
        if isinstance(event.payload, dict):
            raise TypeError(f"dict payload is not allowed for {event.type.value}")
        self._q.put(event)

    def post_payload(self, event_type: EventType | str, payload: Any = None) -> None:
        et = as_event_type(event_type)
        if isinstance(payload, dict):
            raise TypeError(f"dict payload is not allowed for {et.value}")
        self.publish(Event(type=et, payload=payload))

    def post(self, event_type: EventType | str, **kwargs: Any) -> None:
        """
        Allowed for convenience, but DOES NOT enqueue dict payload.
        It converts kwargs -> typed payload for known event types, otherwise:
        - if kwargs is empty: payload=None
        - else: error
        """
        et = as_event_type(event_type)

        # lazy imports avoid cycles
        from core.events.payloads import (
            InfoPayload, StatusPayload, ErrorPayload, ThemeChangePayload,
            DirtyStateChangedPayload,
            RecordUpdatedPayload, RecordDeletedPayload,
            ConfigSavedPayload,
            PickContextRef, PickRequestPayload,
            PickModeEnteredPayload, PickCanceledPayload, PickModeExitedPayload,
        )

        def require(name: str) -> Any:
            if name not in kwargs:
                raise TypeError(f"{et.value} missing required field: {name}")
            return kwargs[name]

        def as_str(v: Any) -> str:
            return v if isinstance(v, str) else str(v)

        # ----- common -----
        if et is EventType.INFO:
            self.post_payload(et, InfoPayload(msg=as_str(require("msg"))))
            return
        if et is EventType.STATUS:
            self.post_payload(et, StatusPayload(msg=as_str(require("msg"))))
            return
        if et is EventType.ERROR:
            msg = as_str(require("msg"))
            detail = as_str(kwargs.get("detail", "") or "")
            code = as_str(kwargs.get("code", "") or "")
            exc = kwargs.get("exc", None) or kwargs.get("exception", None)
            if exc is not None and not detail:
                try:
                    detail = f"{type(exc).__name__}: {exc}"
                except Exception:
                    detail = str(exc)
            self.post_payload(et, ErrorPayload(msg=msg, detail=detail, code=code))
            return
        if et is EventType.UI_THEME_CHANGE:
            self.post_payload(et, ThemeChangePayload(theme=as_str(require("theme"))))
            return

        # ----- dirty -----
        if et is EventType.DIRTY_STATE_CHANGED:
            dirty = bool(require("dirty"))
            parts_raw = require("parts")
            if not isinstance(parts_raw, list):
                raise TypeError("DIRTY_STATE_CHANGED.parts must be a list[str]")
            parts = [as_str(x) for x in parts_raw]
            self.post_payload(et, DirtyStateChangedPayload(dirty=dirty, parts=parts))
            return

        # ----- record events -----
        if et is EventType.RECORD_UPDATED:
            self.post_payload(
                et,
                RecordUpdatedPayload(
                    record_type=as_str(require("record_type")),  # type: ignore[arg-type]
                    id=as_str(require("id")),
                    source=as_str(kwargs.get("source", "") or ""),
                    saved=bool(kwargs.get("saved", False)),
                ),
            )
            return

        if et is EventType.RECORD_DELETED:
            self.post_payload(
                et,
                RecordDeletedPayload(
                    record_type=as_str(require("record_type")),  # type: ignore[arg-type]
                    id=as_str(require("id")),
                    source=as_str(kwargs.get("source", "") or ""),
                    saved=bool(kwargs.get("saved", False)),
                ),
            )
            return

        if et is EventType.CONFIG_SAVED:
            self.post_payload(
                et,
                ConfigSavedPayload(
                    section=as_str(require("section")),  # type: ignore[arg-type]
                    source=as_str(kwargs.get("source", "") or ""),
                    saved=bool(kwargs.get("saved", False)),
                ),
            )
            return

        # ----- pick request/mode (typed; allow dict ctx input but we convert here) -----
        def ctx_ref_from_any(v: Any) -> PickContextRef:
            if isinstance(v, PickContextRef):
                return v
            if isinstance(v, dict):
                t = v.get("type", "")
                i = v.get("id", "")
                if isinstance(t, str) and isinstance(i, str) and i:
                    return PickContextRef(type=t, id=i)  # type: ignore[arg-type]
            raise TypeError(f"{et.value} requires context as PickContextRef or dict{{type,id}}")

        if et is EventType.PICK_REQUEST:
            ctx = ctx_ref_from_any(require("context"))
            self.post_payload(et, PickRequestPayload(context=ctx))
            return

        if et is EventType.PICK_MODE_ENTERED:
            ctx = ctx_ref_from_any(require("context"))
            self.post_payload(et, PickModeEnteredPayload(context=ctx))
            return

        if et is EventType.PICK_CANCELED:
            ctx = ctx_ref_from_any(require("context"))
            self.post_payload(et, PickCanceledPayload(context=ctx))
            return

        if et is EventType.PICK_MODE_EXITED:
            ctx = ctx_ref_from_any(require("context"))
            reason = as_str(kwargs.get("reason", "") or "")
            self.post_payload(et, PickModeExitedPayload(context=ctx, reason=reason))
            return

        # ----- no-payload events -----
        if not kwargs:
            self.post_payload(et, None)
            return

        raise TypeError(f"{et.value} does not support kwargs payload; use post_payload() with a typed payload")

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

    # ---------- dispatch side ----------
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