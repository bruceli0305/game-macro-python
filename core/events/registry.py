# File: core/events/registry.py
from __future__ import annotations

from typing import Any, Dict, Tuple, Type

from core.event_types import EventType
from core.events import payloads as P

PayloadType = Type[Any]


def expected_payload_types() -> Dict[EventType, Tuple[PayloadType, ...]]:
    NONE = (type(None),)

    return {
        # dirty
        EventType.DIRTY_STATE_CHANGED: (P.DirtyStateChangedPayload,),

        # profile
        EventType.PROFILE_CHANGED: (P.ProfileChangedPayload,),
        EventType.PROFILE_LIST_CHANGED: (P.ProfileListChangedPayload,),

        # pick flow
        EventType.PICK_REQUEST: (P.PickRequestPayload,),
        EventType.PICK_CANCEL_REQUEST: NONE,

        EventType.PICK_MODE_ENTERED: (P.PickModeEnteredPayload,),
        EventType.PICK_PREVIEW: (P.PickPreviewPayload,),
        EventType.PICK_CONFIRMED: (P.PickConfirmedPayload,),
        EventType.PICK_CANCELED: (P.PickCanceledPayload,),
        EventType.PICK_MODE_EXITED: (P.PickModeExitedPayload,),
    }


def validate_payload(event_type: EventType, payload: Any) -> None:
    if event_type is EventType.ANY:
        return

    mapping = expected_payload_types()
    allowed = mapping.get(event_type)

    if allowed is None:
        raise TypeError(f"No payload registry entry for event type: {event_type.value}")

    if not isinstance(payload, allowed):
        allowed_names = ", ".join([t.__name__ for t in allowed])
        got = type(payload).__name__
        raise TypeError(f"{event_type.value} payload type mismatch: expected [{allowed_names}], got {got}")