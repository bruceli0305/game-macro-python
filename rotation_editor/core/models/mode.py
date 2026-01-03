from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_list, as_str
from .track import Track


@dataclass
class Mode:
    """
    模式：
    - id: 模式 ID（如 "mode_a"）
    - name: 模式名称（如 "武器A"）
    - tracks: 本模式下的轨道列表
    """
    id: str = ""
    name: str = ""
    tracks: List[Track] = field(default_factory=list)

    # ---------- 反序列化 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Mode":
        d = as_dict(d)
        mid = as_str(d.get("id", ""))
        name = as_str(d.get("name", ""))

        tracks_raw = as_list(d.get("tracks", []))
        tracks: List[Track] = []
        for item in tracks_raw:
            if isinstance(item, dict):
                try:
                    tracks.append(Track.from_dict(item))
                except Exception:
                    # 忽略无法解析的轨道
                    pass

        return Mode(
            id=mid,
            name=name,
            tracks=tracks,
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tracks": [t.to_dict() for t in self.tracks],
        }