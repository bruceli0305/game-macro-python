# File: core/events/payloads.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal


# -------- dirty --------

@dataclass(frozen=True)
class DirtyStateChangedPayload:
    dirty: bool
    parts: List[str]


# -------- profile --------

@dataclass(frozen=True)
class ProfileChangedPayload:
    name: str


@dataclass(frozen=True)
class ProfileListChangedPayload:
    names: List[str]
    current: str


# -------- pick --------

RecordType = Literal["skill_pixel", "point"]


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