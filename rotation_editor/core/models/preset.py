from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_list, as_str, as_int
from .track import Track
from .mode import Mode
from .condition import Condition
from .entry import EntryPoint


@dataclass
class RotationPreset:
    """
    轨道方案（Preset）

    入口字段（新结构）：
    - entry: EntryPoint
        * scope: "global" | "mode"
        * mode_id: scope=="mode" 时必填
        * track_id: 必填
        * node_id: 必填（入口节点）

    为了兼容旧数据：
    - from_dict 仍会读取 entry_mode_id / entry_track_id（若存在），
      并用于补全 entry，但不会在实例上保留这两个字段。
    - to_dict 只输出 "entry"，不再输出 entry_mode_id / entry_track_id。
    """

    id: str = ""
    name: str = ""
    description: str = ""

    # 新入口结构（唯一入口）
    entry: EntryPoint = field(default_factory=EntryPoint)

    global_tracks: List[Track] = field(default_factory=list)
    modes: List[Mode] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)

    max_exec_nodes: int = 0
    max_run_seconds: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RotationPreset":
        d = as_dict(d)
        pid = as_str(d.get("id", ""))
        name = as_str(d.get("name", ""))
        desc = as_str(d.get("description", ""))

        # 旧字段（仅用于兼容）
        legacy_mode_id = as_str(d.get("entry_mode_id", ""))
        legacy_track_id = as_str(d.get("entry_track_id", ""))

        # 新入口读取
        entry_raw = d.get("entry", None)
        if isinstance(entry_raw, dict):
            entry = EntryPoint.from_dict(entry_raw)
            # 兼容旧字段：若 entry 中缺少 mode_id/track_id，则用旧值补齐
            if (legacy_mode_id or "").strip() and not (entry.mode_id or "").strip():
                entry.mode_id = legacy_mode_id.strip()
                entry.scope = "mode"
            if (legacy_track_id or "").strip() and not (entry.track_id or "").strip():
                entry.track_id = legacy_track_id.strip()
        else:
            # 没有 entry：根据旧字段构造一个（node_id 留空，后续由 UI/服务补齐）
            scope = "mode" if (legacy_mode_id or "").strip() else "global"
            entry = EntryPoint(
                scope=scope,
                mode_id=(legacy_mode_id or "").strip() if scope == "mode" else "",
                track_id=(legacy_track_id or "").strip(),
                node_id="",
            )

        max_exec_nodes = as_int(d.get("max_exec_nodes", 0), 0)
        max_run_seconds = as_int(d.get("max_run_seconds", 0), 0)

        gtracks_raw = as_list(d.get("global_tracks", []))
        gtracks: List[Track] = []
        for item in gtracks_raw:
            if isinstance(item, dict):
                try:
                    gtracks.append(Track.from_dict(item))
                except Exception:
                    pass

        modes_raw = as_list(d.get("modes", []))
        modes: List[Mode] = []
        for item in modes_raw:
            if isinstance(item, dict):
                try:
                    modes.append(Mode.from_dict(item))
                except Exception:
                    pass

        conds_raw = as_list(d.get("conditions", []))
        conds: List[Condition] = []
        for item in conds_raw:
            if isinstance(item, dict):
                try:
                    conds.append(Condition.from_dict(item))
                except Exception:
                    pass

        return RotationPreset(
            id=pid,
            name=name,
            description=desc,
            entry=entry,
            global_tracks=gtracks,
            modes=modes,
            conditions=conds,
            max_exec_nodes=max_exec_nodes,
            max_run_seconds=max_run_seconds,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        仅输出新的 entry 结构，不再写出旧字段 entry_mode_id / entry_track_id。
        """
        entry_out = self.entry.to_dict() if self.entry is not None else EntryPoint().to_dict()

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entry": entry_out,
            "global_tracks": [t.to_dict() for t in self.global_tracks],
            "modes": [m.to_dict() for m in self.modes],
            "conditions": [c.to_dict() for c in self.conditions],
            "max_exec_nodes": int(self.max_exec_nodes),
            "max_run_seconds": int(self.max_run_seconds),
        }