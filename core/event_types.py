from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """
    Centralized event types.

    Note:
    - Inherit from str so it's easy to print/serialize.
    - Use EventType.ANY as wildcard subscription.
    """

    ANY = "*"

    # common messages
    INFO = "INFO"
    ERROR = "ERROR"
    STATUS = "STATUS"

    # ui/config
    UI_THEME_CHANGE = "UI_THEME_CHANGE"
    HOTKEYS_CHANGED = "HOTKEYS_CHANGED"

    # pick flow
    PICK_REQUEST = "PICK_REQUEST"
    PICK_START_LAST = "PICK_START_LAST"
    PICK_CANCEL_REQUEST = "PICK_CANCEL_REQUEST"

    PICK_MODE_ENTERED = "PICK_MODE_ENTERED"
    PICK_PREVIEW = "PICK_PREVIEW"
    PICK_CONFIRMED = "PICK_CONFIRMED"
    PICK_CANCELED = "PICK_CANCELED"
    PICK_MODE_EXITED = "PICK_MODE_EXITED"

    def __str__(self) -> str:
        return self.value


def as_event_type(t: EventType | str) -> EventType:
    """
    Convert a string (or EventType) into EventType.
    Keeps backward compatibility during migration.
    """
    if isinstance(t, EventType):
        return t

    s = (t or "").strip()
    if s == "*":
        return EventType.ANY

    try:
        return EventType(s)
    except ValueError as e:
        raise ValueError(f"Unknown event type: {t!r}") from e