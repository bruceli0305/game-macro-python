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

    入口字段（当前阶段同时存在两套）：
    - entry: 新入口结构（后续引擎会严格使用）
    - entry_mode_id / entry_track_id: 旧入口字段（现有 UI/服务仍在用）
      本次重构第一步暂时保留，避免一次性改动太大；后续步骤会彻底移除旧字段。

    其他：
    - global_tracks / modes / conditions
    - max_exec_nodes / max_run_seconds
    """

    id: str = ""
    name: str = ""
    description: str = ""

    # 新入口结构（后续会成为唯一入口）
    entry: EntryPoint = field(default_factory=EntryPoint)

    # 旧入口字段（暂存，用于现有 UI）
    entry_mode_id: str = ""
    entry_track_id: str = ""

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

        # 旧字段读取（现有数据/现有 UI）
        entry_mode_id = as_str(d.get("entry_mode_id", ""))
        entry_track_id = as_str(d.get("entry_track_id", ""))

        # 新入口读取
        entry_raw = d.get("entry", None)
        if isinstance(entry_raw, dict):
            entry = EntryPoint.from_dict(entry_raw)
        else:
            # 若没有 entry，则根据旧字段构造一个（node_id 为空，后续步骤会补齐并最终移除旧字段）
            scope = "mode" if (entry_mode_id or "").strip() else "global"
            entry = EntryPoint(
                scope=scope,
                mode_id=(entry_mode_id or "").strip(),
                track_id=(entry_track_id or "").strip(),
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

        # 尽量保持新旧字段一致（旧 UI 仍在写旧字段）
        if (entry.mode_id or "").strip() and not (entry_mode_id or "").strip():
            entry_mode_id = entry.mode_id
        if (entry.track_id or "").strip() and not (entry_track_id or "").strip():
            entry_track_id = entry.track_id

        return RotationPreset(
            id=pid,
            name=name,
            description=desc,
            entry=entry,
            entry_mode_id=entry_mode_id,
            entry_track_id=entry_track_id,
            global_tracks=gtracks,
            modes=modes,
            conditions=conds,
            max_exec_nodes=max_exec_nodes,
            max_run_seconds=max_run_seconds,
        )

    def to_dict(self) -> Dict[str, Any]:
        # 现阶段：旧字段仍是 UI 的事实来源，因此序列化时以旧字段为准同步 entry（避免 entry 漂移）
        em = (self.entry_mode_id or "").strip()
        et = (self.entry_track_id or "").strip()

        entry_out = self.entry.to_dict() if self.entry is not None else EntryPoint().to_dict()

        # 用旧字段覆盖 entry 的 scope/mode_id/track_id（node_id 暂不强制）
        if em:
            entry_out["scope"] = "mode"
            entry_out["mode_id"] = em
            entry_out["track_id"] = et
        else:
            entry_out["scope"] = "global"
            entry_out["mode_id"] = ""
            entry_out["track_id"] = et

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,

            # 新入口结构
            "entry": entry_out,

            # 旧入口字段（暂时保留，后续步骤会移除）
            "entry_mode_id": self.entry_mode_id,
            "entry_track_id": self.entry_track_id,

            "global_tracks": [t.to_dict() for t in self.global_tracks],
            "modes": [m.to_dict() for m in self.modes],
            "conditions": [c.to_dict() for c in self.conditions],
            "max_exec_nodes": int(self.max_exec_nodes),
            "max_run_seconds": int(self.max_run_seconds),
        }