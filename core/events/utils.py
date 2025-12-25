from __future__ import annotations

from typing import Any, Optional, Tuple, List

from core.events.payloads import (
    DirtyStateChangedPayload,
    RecordUpdatedPayload,
    RecordDeletedPayload,
    ConfigSavedPayload,
    PickPreviewPayload,
    PickConfirmedPayload,
    InfoPayload,
    StatusPayload,
    ErrorPayload,
    ThemeChangePayload,
)


def dirty_state_from_payload(payload: Any) -> Tuple[bool, List[str]]:
    if isinstance(payload, DirtyStateChangedPayload):
        return payload.dirty, list(payload.parts)
    return False, []


def record_updated_from_payload(payload: Any) -> Optional[RecordUpdatedPayload]:
    return payload if isinstance(payload, RecordUpdatedPayload) else None


def record_deleted_from_payload(payload: Any) -> Optional[RecordDeletedPayload]:
    return payload if isinstance(payload, RecordDeletedPayload) else None


def config_saved_from_payload(payload: Any) -> Optional[ConfigSavedPayload]:
    return payload if isinstance(payload, ConfigSavedPayload) else None


def pick_preview_from_payload(payload: Any) -> Optional[PickPreviewPayload]:
    return payload if isinstance(payload, PickPreviewPayload) else None


def pick_confirmed_from_payload(payload: Any) -> Optional[PickConfirmedPayload]:
    return payload if isinstance(payload, PickConfirmedPayload) else None


def info_from_payload(payload: Any) -> Optional[str]:
    return payload.msg if isinstance(payload, InfoPayload) else None


def status_from_payload(payload: Any) -> Optional[str]:
    return payload.msg if isinstance(payload, StatusPayload) else None


def error_from_payload(payload: Any) -> Optional[Tuple[str, str, str]]:
    if isinstance(payload, ErrorPayload):
        return (payload.msg, payload.detail, payload.code)
    return None


def theme_from_payload(payload: Any) -> Optional[str]:
    return payload.theme if isinstance(payload, ThemeChangePayload) else None