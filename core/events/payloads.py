from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional


# -------- common UI messages --------

@dataclass(frozen=True)
class InfoPayload:
    msg: str


@dataclass(frozen=True)
class StatusPayload:
    msg: str


@dataclass(frozen=True)
class ErrorPayload:
    msg: str
    detail: str = ""
    code: str = ""


@dataclass(frozen=True)
class ThemeChangePayload:
    theme: str


# -------- application-level payloads --------

RecordType = Literal["skill_pixel", "point"]
ConfigSection = Literal["base"]


@dataclass(frozen=True)
class DirtyStateChangedPayload:
    dirty: bool
    parts: List[str]


@dataclass(frozen=True)
class RecordUpdatedPayload:
    record_type: RecordType
    id: str
    source: str = ""
    saved: bool = False


@dataclass(frozen=True)
class RecordDeletedPayload:
    record_type: RecordType
    id: str
    source: str = ""
    saved: bool = False


@dataclass(frozen=True)
class ConfigSavedPayload:
    section: ConfigSection
    source: str = ""
    saved: bool = False


# -------- pick payloads --------

@dataclass(frozen=True)
class PickContextRef:
    type: RecordType
    id: str


@dataclass(frozen=True)
class PickRequestPayload:
    context: PickContextRef


@dataclass(frozen=True)
class PickModeEnteredPayload:
    context: PickContextRef


@dataclass(frozen=True)
class PickCanceledPayload:
    context: PickContextRef


@dataclass(frozen=True)
class PickModeExitedPayload:
    context: PickContextRef
    reason: str = ""


@dataclass(frozen=True)
class PickPreviewPayload:
    context: PickContextRef
    monitor_requested: str
    monitor: str
    inside: bool

    x: int
    y: int

    vx: int
    vy: int

    abs_x: int
    abs_y: int

    r: int
    g: int
    b: int
    hex: str


@dataclass(frozen=True)
class PickConfirmedPayload(PickPreviewPayload):
    pass