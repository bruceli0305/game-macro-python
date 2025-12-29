# File: core/pick/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.pick.capture import SampleSpec

RecordType = Literal["skill_pixel", "point"]


@dataclass(frozen=True)
class PickSessionConfig:
    record_type: RecordType
    record_id: str

    monitor_requested: str
    sample: SampleSpec

    delay_ms: int
    preview_throttle_ms: int
    error_throttle_ms: int

    confirm_hotkey: str

    mouse_avoid: bool
    mouse_avoid_offset_y: int
    mouse_avoid_settle_ms: int


@dataclass(frozen=True)
class PickPreview:
    record_type: RecordType
    record_id: str

    monitor_requested: str
    monitor: str
    inside: bool

    # rel (within monitor)
    x: int
    y: int

    # abs (virtual screen)
    vx: int
    vy: int

    r: int
    g: int
    b: int
    hex: str


@dataclass(frozen=True)
class PickConfirmed(PickPreview):
    pass