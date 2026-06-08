from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class WindowState:
    width: int = 1100
    height: int = 720
    x: Optional[int] = None
    y: Optional[int] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WindowState":
        return WindowState(
            width=int(d.get("width", 1100)),
            height=int(d.get("height", 720)),
            x=d.get("x", None),
            y=d.get("y", None),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"width": int(self.width), "height": int(self.height)}
        if self.x is not None:
            out["x"] = int(self.x)
        if self.y is not None:
            out["y"] = int(self.y)
        return out


@dataclass
class AppState:
    schema_version: int = 1
    last_profile: str = ""
    worker_id: int = 0
    window: WindowState = field(default_factory=WindowState)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AppState":
        return AppState(
            schema_version=int(d.get("schema_version", 1)),
            last_profile=str(d.get("last_profile", "")),
            worker_id=int(d.get("worker_id", 0)),
            window=WindowState.from_dict(d.get("window", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "last_profile": self.last_profile,
            "worker_id": int(self.worker_id),
            "window": self.window.to_dict(),
        }