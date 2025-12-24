from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_int, as_list, as_str, clamp_int
from core.models.skill import ColorRGB, SampleConfig  # 复用颜色/采样结构


@dataclass
class Point:
    id: str = ""          # snowflake id string
    name: str = ""
    monitor: str = "primary"
    x: int = 0
    y: int = 0
    color: ColorRGB = field(default_factory=ColorRGB)
    sample: SampleConfig = field(default_factory=SampleConfig)
    captured_at: str = ""  # ISO string
    note: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Point":
        d = as_dict(d)
        return Point(
            id=as_str(d.get("id", "")),
            name=as_str(d.get("name", "")),
            monitor=as_str(d.get("monitor", "primary"), "primary"),
            x=clamp_int(as_int(d.get("x", 0), 0), 0, 10**9),
            y=clamp_int(as_int(d.get("y", 0), 0), 0, 10**9),
            color=ColorRGB.from_dict(d.get("color", {}) or {}),
            sample=SampleConfig.from_dict(d.get("sample", {}) or {}),
            captured_at=as_str(d.get("captured_at", "")),
            note=as_str(d.get("note", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "monitor": self.monitor,
            "x": int(self.x),
            "y": int(self.y),
            "color": self.color.to_dict(),
            "sample": self.sample.to_dict(),
            "captured_at": self.captured_at,
            "note": self.note,
        }


@dataclass
class PointsFile:
    schema_version: int = 1
    points: List[Point] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PointsFile":
        d = as_dict(d)
        points_raw = as_list(d.get("points", []))
        points: List[Point] = []
        for item in points_raw:
            if isinstance(item, dict):
                points.append(Point.from_dict(item))
        return PointsFile(
            schema_version=as_int(d.get("schema_version", 1), 1),
            points=points,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "points": [p.to_dict() for p in self.points],
        }