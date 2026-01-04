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

    # confirm pick by hotkey (Esc is fixed cancel in PickService)
    confirm_hotkey: str = "f8"

    # mouse avoidance: move mouse away (Y-axis) before sampling the original point
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
    施法完成判定策略（全局配置）：

    - mode: "timer" | "bar"
        * "timer": 仅按技能的 readbar_ms 等待
        * "bar":   使用施法条像素点位判断释放完成
    - point_id: 若 mode="bar"，引用 PointsFile 中的一个点位 ID 作为
                “施法条读满时”的颜色基准
    - tolerance: 颜色容差，0..255
    """
    mode: str = "timer"
    point_id: str = ""
    tolerance: int = 15

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CastBarConfig":
        d = as_dict(d)
        mode = as_str(d.get("mode", "timer"), "timer").strip().lower()
        if mode not in ("timer", "bar"):
            mode = "timer"
        tol = clamp_int(as_int(d.get("tolerance", 15), 15), 0, 255)
        return CastBarConfig(
            mode=mode,
            point_id=as_str(d.get("point_id", "")),
            tolerance=tol,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "point_id": self.point_id,
            "tolerance": int(self.tolerance),
        }


@dataclass
class ExecConfig:
    """
    执行策略（宏引擎）相关配置：

    - enabled: 是否启用执行启停热键
    - toggle_hotkey: 启停热键（全局），由后续全局热键监听使用
        * 空串或 enabled=False 表示禁用
        * 格式同其他热键，使用 normalize() 规范化
    - default_skill_gap_ms: 每个技能执行完成后到下一个节点之间的默认间隔
        * 0 表示“尽快”（不主动插入 sleep）
    """
    enabled: bool = False
    toggle_hotkey: str = ""  # 例如 "f9" / "ctrl+f9"
    default_skill_gap_ms: int = 50

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ExecConfig":
        d = as_dict(d)
        return ExecConfig(
            enabled=as_bool(d.get("enabled", False), False),
            toggle_hotkey=as_str(d.get("toggle_hotkey", ""), ""),
            default_skill_gap_ms=clamp_int(as_int(d.get("default_skill_gap_ms", 50), 50), 0, 10**6),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "toggle_hotkey": self.toggle_hotkey,
            "default_skill_gap_ms": int(self.default_skill_gap_ms),
        }

@dataclass
class BaseFile:
    """
    Represents base.json root object.

    Step 4 change:
    - 删除 hotkeys 字段（不再存在全局进入/取消取色热键）
    """
    schema_version: int = 2
    ui: UIConfig = field(default_factory=UIConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    pick: PickConfig = field(default_factory=PickConfig)
    io: IOConfig = field(default_factory=IOConfig)
    # 施法完成策略（定时 / 施法条像素）
    cast_bar: CastBarConfig = field(default_factory=CastBarConfig)
    # 执行策略（启停热键等）
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