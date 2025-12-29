# File: core/event_types.py
from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """
    Step 3-3-3-3-6:
    EventBus 只保留“信号类事件”：
    - dirty state
    - profile change (可选，但目前保留)
    - pick flow
    """

    ANY = "*"

    # dirty state
    DIRTY_STATE_CHANGED = "DIRTY_STATE_CHANGED"  # payload: DirtyStateChangedPayload

    # profile (still kept)
    PROFILE_LIST_CHANGED = "PROFILE_LIST_CHANGED"  # payload: ProfileListChangedPayload
    PROFILE_CHANGED = "PROFILE_CHANGED"            # payload: ProfileChangedPayload

    # pick flow
    PICK_REQUEST = "PICK_REQUEST"                  # payload: PickRequestPayload
    PICK_CANCEL_REQUEST = "PICK_CANCEL_REQUEST"    # payload: None

    PICK_MODE_ENTERED = "PICK_MODE_ENTERED"        # payload: PickModeEnteredPayload
    PICK_PREVIEW = "PICK_PREVIEW"                  # payload: PickPreviewPayload
    PICK_CONFIRMED = "PICK_CONFIRMED"              # payload: PickConfirmedPayload
    PICK_CANCELED = "PICK_CANCELED"                # payload: PickCanceledPayload
    PICK_MODE_EXITED = "PICK_MODE_EXITED"          # payload: PickModeExitedPayload

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