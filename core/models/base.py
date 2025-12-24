from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from core.models.common import as_bool, as_dict, as_int, as_int_tuple2, as_str, clamp_int


@dataclass
class UIConfig:
    theme: str = "darkly"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "UIConfig":
        d = as_dict(d)
        return UIConfig(theme=as_str(d.get("theme", "darkly"), "darkly"))

    def to_dict(self) -> Dict[str, Any]:
        return {"theme": self.theme}


@dataclass
class CaptureConfig:
    monitor_policy: str = "primary"  # "primary" | "all" | "monitor_1" ...

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CaptureConfig":
        d = as_dict(d)
        return CaptureConfig(monitor_policy=as_str(d.get("monitor_policy", "primary"), "primary"))

    def to_dict(self) -> Dict[str, Any]:
        return {"monitor_policy": self.monitor_policy}


@dataclass
class HotkeysConfig:
    enter_pick_mode: str = "ctrl+alt+p"
    cancel_pick: str = "esc"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "HotkeysConfig":
        d = as_dict(d)
        return HotkeysConfig(
            enter_pick_mode=as_str(d.get("enter_pick_mode", "ctrl+alt+p"), "ctrl+alt+p"),
            cancel_pick=as_str(d.get("cancel_pick", "esc"), "esc"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enter_pick_mode": self.enter_pick_mode,
            "cancel_pick": self.cancel_pick,
        }


@dataclass
class PickAvoidanceConfig:
    mode: str = "hide_main"  # "hide_main" | "minimize" | "move_aside" | "none"
    delay_ms: int = 120
    preview_follow_cursor: bool = True
    preview_offset: Tuple[int, int] = (30, 30)
    preview_anchor: str = "bottom_right"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PickAvoidanceConfig":
        d = as_dict(d)
        return PickAvoidanceConfig(
            mode=as_str(d.get("mode", "hide_main"), "hide_main"),
            delay_ms=clamp_int(as_int(d.get("delay_ms", 120), 120), 0, 5000),
            preview_follow_cursor=as_bool(d.get("preview_follow_cursor", True), True),
            preview_offset=as_int_tuple2(d.get("preview_offset", (30, 30)), (30, 30)),
            preview_anchor=as_str(d.get("preview_anchor", "bottom_right"), "bottom_right"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "delay_ms": int(self.delay_ms),
            "preview_follow_cursor": bool(self.preview_follow_cursor),
            "preview_offset": [int(self.preview_offset[0]), int(self.preview_offset[1])],
            "preview_anchor": self.preview_anchor,
        }


@dataclass
class PickConfig:
    avoidance: PickAvoidanceConfig = field(default_factory=PickAvoidanceConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PickConfig":
        d = as_dict(d)
        return PickConfig(
            avoidance=PickAvoidanceConfig.from_dict(d.get("avoidance", {}) or {})
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"avoidance": self.avoidance.to_dict()}


@dataclass
class IOConfig:
    auto_save: bool = True
    backup_on_save: bool = True

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "IOConfig":
        d = as_dict(d)
        return IOConfig(
            auto_save=as_bool(d.get("auto_save", True), True),
            backup_on_save=as_bool(d.get("backup_on_save", True), True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "auto_save": bool(self.auto_save),
            "backup_on_save": bool(self.backup_on_save),
        }


@dataclass
class BaseFile:
    """
    Represents base.json root object.
    """
    schema_version: int = 1
    ui: UIConfig = field(default_factory=UIConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    hotkeys: HotkeysConfig = field(default_factory=HotkeysConfig)
    pick: PickConfig = field(default_factory=PickConfig)
    io: IOConfig = field(default_factory=IOConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BaseFile":
        d = as_dict(d)
        return BaseFile(
            schema_version=as_int(d.get("schema_version", 1), 1),
            ui=UIConfig.from_dict(d.get("ui", {}) or {}),
            capture=CaptureConfig.from_dict(d.get("capture", {}) or {}),
            hotkeys=HotkeysConfig.from_dict(d.get("hotkeys", {}) or {}),
            pick=PickConfig.from_dict(d.get("pick", {}) or {}),
            io=IOConfig.from_dict(d.get("io", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "ui": self.ui.to_dict(),
            "capture": self.capture.to_dict(),
            "hotkeys": self.hotkeys.to_dict(),
            "pick": self.pick.to_dict(),
            "io": self.io.to_dict(),
        }