# File: core/event_types.py
from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """
    Step 3-3-3-3-7:
    EventBus 仅保留：
    - dirty state
    - pick flow
    """

    ANY = "*"

    # dirty state
    DIRTY_STATE_CHANGED = "DIRTY_STATE_CHANGED"

    # pick flow
    PICK_REQUEST = "PICK_REQUEST"
    PICK_CANCEL_REQUEST = "PICK_CANCEL_REQUEST"

    PICK_MODE_ENTERED = "PICK_MODE_ENTERED"
    PICK_PREVIEW = "PICK_PREVIEW"
    PICK_CONFIRMED = "PICK_CONFIRMED"
    PICK_CANCELED = "PICK_CANCELED"
    PICK_MODE_EXITED = "PICK_MODE_EXITED"

    def __str__(self) -> str:
        return self.value


def as_event_type(t: "EventType | str") -> EventType:
    if isinstance(t, EventType):
        return t

    s = (t or "").strip()
    if s == "*":
        return EventType.ANY

    try:
        return EventType(s)
    except ValueError as e:
        raise ValueError(f"Unknown event type: {t!r}") from e