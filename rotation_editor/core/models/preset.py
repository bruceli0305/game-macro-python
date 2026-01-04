from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_list, as_str, as_int
from .track import Track
from .mode import Mode
from .condition import Condition


@dataclass
class RotationPreset:
    """
    轨道方案（Preset）：

    - id: 唯一 ID（UUID 等）
    - name: 名称
    - description: 描述（备注）
    - entry_mode_id: 入口模式 ID（空表示从全局轨道入口）
    - entry_track_id: 入口轨道 ID（可为空，表示不指定）
    - global_tracks: 全局轨道列表
    - modes: 模式列表，每个模式下有自己的 tracks
    - conditions: 条件列表，供 GatewayNode.condition_id 引用

    新增：
    - max_exec_nodes: 最大执行节点次数（0 表示无限制）
    - max_run_seconds: 最长运行时间（秒，0 表示无限制）
    """
    id: str = ""
    name: str = ""
    description: str = ""

    entry_mode_id: str = ""
    entry_track_id: str = ""

    global_tracks: List[Track] = field(default_factory=list)
    modes: List[Mode] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)

    max_exec_nodes: int = 0
    max_run_seconds: int = 0

    # ---------- 反序列化 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RotationPreset":
        d = as_dict(d)
        pid = as_str(d.get("id", ""))
        name = as_str(d.get("name", ""))
        desc = as_str(d.get("description", ""))
        entry_mode_id = as_str(d.get("entry_mode_id", ""))
        entry_track_id = as_str(d.get("entry_track_id", ""))

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
            entry_mode_id=entry_mode_id,
            entry_track_id=entry_track_id,
            global_tracks=gtracks,
            modes=modes,
            conditions=conds,
            max_exec_nodes=max_exec_nodes,
            max_run_seconds=max_run_seconds,
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entry_mode_id": self.entry_mode_id,
            "entry_track_id": self.entry_track_id,
            "global_tracks": [t.to_dict() for t in self.global_tracks],
            "modes": [m.to_dict() for m in self.modes],
            "conditions": [c.to_dict() for c in self.conditions],
            "max_exec_nodes": int(self.max_exec_nodes),
            "max_run_seconds": int(self.max_run_seconds),
        }