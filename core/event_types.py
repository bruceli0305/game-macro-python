# File: core/event_types.py
from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    ANY = "*"

    # common messages
    INFO = "INFO"
    ERROR = "ERROR"
    STATUS = "STATUS"

    # ui/config
    UI_THEME_CHANGE = "UI_THEME_CHANGE"

    # pick flow
    PICK_REQUEST = "PICK_REQUEST"
    PICK_CANCEL_REQUEST = "PICK_CANCEL_REQUEST"

    PICK_MODE_ENTERED = "PICK_MODE_ENTERED"
    PICK_PREVIEW = "PICK_PREVIEW"
    PICK_CONFIRMED = "PICK_CONFIRMED"
    PICK_CANCELED = "PICK_CANCELED"
    PICK_MODE_EXITED = "PICK_MODE_EXITED"

    # application-level
    RECORD_UPDATED = "RECORD_UPDATED"
    RECORD_DELETED = "RECORD_DELETED"  # payload: record_type, id, source, saved
    CONFIG_SAVED = "CONFIG_SAVED"      # payload: section(str), source(str), saved(bool)

    PROFILE_LIST_CHANGED = "PROFILE_LIST_CHANGED"  # payload: names(list[str]), current(str)
    PROFILE_CHANGED = "PROFILE_CHANGED"            # payload: name(str)

    # dirty state
    DIRTY_STATE_CHANGED = "DIRTY_STATE_CHANGED"  # payload: dirty(bool), parts(list[str])

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