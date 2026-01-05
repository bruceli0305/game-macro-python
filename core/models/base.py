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
class PickAvoidanceConfig:
    """
    Window avoidance + preview UX config.
    """
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
    """
    pick config root.

    - confirm_hotkey: 取色确认热键（Esc 固定为取消）
    - mouse_avoid: 鼠标避让配置
    """
    avoidance: PickAvoidanceConfig = field(default_factory=PickAvoidanceConfig)

    confirm_hotkey: str = "f8"

    mouse_avoid: bool = True
    mouse_avoid_offset_y: int = 80
    mouse_avoid_settle_ms: int = 80

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PickConfig":
        d = as_dict(d)
        return PickConfig(
            avoidance=PickAvoidanceConfig.from_dict(d.get("avoidance", {}) or {}),
            confirm_hotkey=as_str(d.get("confirm_hotkey", "f8"), "f8"),
            mouse_avoid=as_bool(d.get("mouse_avoid", True), True),
            mouse_avoid_offset_y=clamp_int(as_int(d.get("mouse_avoid_offset_y", 80), 80), 0, 500),
            mouse_avoid_settle_ms=clamp_int(as_int(d.get("mouse_avoid_settle_ms", 80), 80), 0, 500),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avoidance": self.avoidance.to_dict(),
            "confirm_hotkey": self.confirm_hotkey,
            "mouse_avoid": bool(self.mouse_avoid),
            "mouse_avoid_offset_y": int(self.mouse_avoid_offset_y),
            "mouse_avoid_settle_ms": int(self.mouse_avoid_settle_ms),
        }


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
class CastBarConfig:
    """
    施法完成判定策略（全局配置）
    """
    mode: str = "timer"
    point_id: str = ""
    tolerance: int = 15
    poll_interval_ms: int = 30
    max_wait_factor: float = 1.5

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CastBarConfig":
        d = as_dict(d)
        mode = as_str(d.get("mode", "timer"), "timer").strip().lower()
        if mode not in ("timer", "bar"):
            mode = "timer"

        tol = clamp_int(as_int(d.get("tolerance", 15), 15), 0, 255)
        poll = clamp_int(as_int(d.get("poll_interval_ms", 30), 30), 10, 1000)

        raw_factor = d.get("max_wait_factor", 1.5)
        try:
            factor = float(raw_factor)
        except Exception:
            factor = 1.5
        if factor < 0.1:
            factor = 0.1
        if factor > 10.0:
            factor = 10.0

        return CastBarConfig(
            mode=mode,
            point_id=as_str(d.get("point_id", "")),
            tolerance=tol,
            poll_interval_ms=poll,
            max_wait_factor=factor,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "point_id": self.point_id,
            "tolerance": int(self.tolerance),
            "poll_interval_ms": int(self.poll_interval_ms),
            "max_wait_factor": float(self.max_wait_factor),
        }


@dataclass
class ExecConfig:
    """
    执行策略（宏引擎）相关配置：

    - enabled / toggle_hotkey: 全局启停热键（仅热键控制用）
    - default_skill_gap_ms: 技能成功/失败后到下一个节点间隔

    新增（施法状态机 / 轮询 / 重试）：
    - poll_not_ready_ms: ready=False 时的轮询间隔（推进节点，下轮 cycle 再判断）
    - start_signal_mode: "pixel" | "cast_bar" | "none"
    - start_timeout_ms / start_poll_ms: PREPARING -> CASTING 的判定窗口与轮询间隔
    - max_retries / retry_gap_ms: 进入 CASTING 失败时的重试参数
    """
    enabled: bool = False
    toggle_hotkey: str = ""
    default_skill_gap_ms: int = 50

    poll_not_ready_ms: int = 50
    start_signal_mode: str = "pixel"   # "pixel" | "cast_bar" | "none"
    start_timeout_ms: int = 20
    start_poll_ms: int = 10
    max_retries: int = 3
    retry_gap_ms: int = 30

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ExecConfig":
        d = as_dict(d)

        mode = as_str(d.get("start_signal_mode", "pixel"), "pixel").strip().lower()
        if mode not in ("pixel", "cast_bar", "none"):
            mode = "pixel"

        return ExecConfig(
            enabled=as_bool(d.get("enabled", False), False),
            toggle_hotkey=as_str(d.get("toggle_hotkey", ""), ""),
            default_skill_gap_ms=clamp_int(as_int(d.get("default_skill_gap_ms", 50), 50), 0, 10**6),

            poll_not_ready_ms=clamp_int(as_int(d.get("poll_not_ready_ms", 50), 50), 10, 10**6),
            start_signal_mode=mode,
            start_timeout_ms=clamp_int(as_int(d.get("start_timeout_ms", 20), 20), 1, 10**6),
            start_poll_ms=clamp_int(as_int(d.get("start_poll_ms", 10), 10), 5, 10**6),
            max_retries=clamp_int(as_int(d.get("max_retries", 3), 3), 0, 1000),
            retry_gap_ms=clamp_int(as_int(d.get("retry_gap_ms", 30), 30), 0, 10**6),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "toggle_hotkey": self.toggle_hotkey,
            "default_skill_gap_ms": int(self.default_skill_gap_ms),

            "poll_not_ready_ms": int(self.poll_not_ready_ms),
            "start_signal_mode": self.start_signal_mode,
            "start_timeout_ms": int(self.start_timeout_ms),
            "start_poll_ms": int(self.start_poll_ms),
            "max_retries": int(self.max_retries),
            "retry_gap_ms": int(self.retry_gap_ms),
        }


@dataclass
class BaseFile:
    """
    Represents base.json root object.
    """
    schema_version: int = 2
    ui: UIConfig = field(default_factory=UIConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    pick: PickConfig = field(default_factory=PickConfig)
    io: IOConfig = field(default_factory=IOConfig)
    cast_bar: CastBarConfig = field(default_factory=CastBarConfig)
    exec: ExecConfig = field(default_factory=ExecConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BaseFile":
        d = as_dict(d)
        return BaseFile(
            schema_version=as_int(d.get("schema_version", 2), 2),
            ui=UIConfig.from_dict(d.get("ui", {}) or {}),
            capture=CaptureConfig.from_dict(d.get("capture", {}) or {}),
            pick=PickConfig.from_dict(d.get("pick", {}) or {}),
            io=IOConfig.from_dict(d.get("io", {}) or {}),
            cast_bar=CastBarConfig.from_dict(d.get("cast_bar", {}) or {}),
            exec=ExecConfig.from_dict(d.get("exec", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "ui": self.ui.to_dict(),
            "capture": self.capture.to_dict(),
            "pick": self.pick.to_dict(),
            "io": self.io.to_dict(),
            "cast_bar": self.cast_bar.to_dict(),
            "exec": self.exec.to_dict(),
        }