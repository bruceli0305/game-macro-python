# rotation_editor/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.models.common import as_dict, as_list, as_str, as_int


# ---------- Condition ----------

@dataclass
class Condition:
    """
    条件定义（占位结构）：
    - id: 条件唯一 ID，供节点引用
    - name: 简短名称，UI 展示用
    - kind: 条件类型（例如 "pixel" / "buff_remain_lt" / "hp_lt" / "expr"...）
    - expr: 具体参数（结构后续可扩展）
    """
    id: str = ""
    name: str = ""
    kind: str = ""
    expr: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Condition":
        d = as_dict(d)
        return Condition(
            id=as_str(d.get("id", "")),
            name=as_str(d.get("name", "")),
            kind=as_str(d.get("kind", "")),
            expr=as_dict(d.get("expr", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "expr": dict(self.expr or {}),
        }


# ---------- Node 基类 ----------

@dataclass
class Node:
    """
    轨道节点基类：

    - kind: "skill" | "gateway" | ...
    - id: 节点 ID
    - label: UI 上展示用的短标签（例如 "2" / "A→B" 等）

    实际使用时一般是 SkillNode 或 GatewayNode 子类。
    """
    id: str = ""
    kind: str = "skill"
    label: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Node":
        """
        工厂方法：根据 kind 字段分发到具体子类。
        """
        d = as_dict(d)
        kind = as_str(d.get("kind", "skill"), "skill").strip().lower()
        if kind == "gateway":
            return GatewayNode.from_dict(d)
        # 默认当作 skill 节点处理
        return SkillNode.from_dict(d)

    def to_dict(self) -> Dict[str, Any]:
        """
        子类应覆写本方法；这里只做兜底。
        """
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
        }


# ---------- SkillNode ----------

@dataclass
class SkillNode(Node):
    """
    技能节点：
    - skill_id: 引用 skills.json 中的 Skill.id
    - override_cast_ms: 可选，覆盖 Skill.cast.readbar_ms
    - comment: 备注（UI 展示用）
    """
    skill_id: str = ""
    override_cast_ms: Optional[int] = None
    comment: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SkillNode":
        d = as_dict(d)
        node_id = as_str(d.get("id", ""))
        label = as_str(d.get("label", ""))

        skill_id = as_str(d.get("skill_id", ""))
        oc_raw = d.get("override_cast_ms", None)
        if oc_raw is None:
            override_cast_ms: Optional[int] = None
        else:
            v = as_int(oc_raw, 0)
            override_cast_ms = v if v >= 0 else None

        comment = as_str(d.get("comment", ""))

        return SkillNode(
            id=node_id,
            kind="skill",
            label=label,
            skill_id=skill_id,
            override_cast_ms=override_cast_ms,
            comment=comment,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": "skill",
            "label": self.label,
            "skill_id": self.skill_id,
            "comment": self.comment,
        }
        if self.override_cast_ms is not None:
            out["override_cast_ms"] = int(self.override_cast_ms)
        return out


# ---------- GatewayNode ----------

@dataclass
class GatewayNode(Node):
    """
    网关节点（控制流节点，不直接放技能）：

    - condition_id: 条件 ID（可选），为空则无条件，执行到此节点即触发动作
    - action: 动作类型，MVP 先支持：
        - "switch_mode": 切换到另一个模式
      预留:
        - "jump_track": 跳转到当前/其他轨道
        - "jump_node": 跳转到当前轨道某个节点索引
        - "end": 结束当前模式/轨道
    - target_mode_id / target_track_id / target_node_index:
        动作需要的目标参数（视 action 而定）
    """
    condition_id: Optional[str] = None
    action: str = "switch_mode"
    target_mode_id: Optional[str] = None
    target_track_id: Optional[str] = None
    target_node_index: Optional[int] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GatewayNode":
        d = as_dict(d)
        node_id = as_str(d.get("id", ""))
        label = as_str(d.get("label", ""))

        cond_id = d.get("condition_id", None)
        if cond_id is not None:
            cond_id = as_str(cond_id, "")

        action = as_str(d.get("action", "switch_mode"), "switch_mode").strip() or "switch_mode"

        t_mode = d.get("target_mode_id", None)
        if t_mode is not None:
            t_mode = as_str(t_mode, "")

        t_track = d.get("target_track_id", None)
        if t_track is not None:
            t_track = as_str(t_track, "")

        idx_raw = d.get("target_node_index", None)
        if idx_raw is None:
            t_index: Optional[int] = None
        else:
            v = as_int(idx_raw, -1)
            t_index = v if v >= 0 else None

        return GatewayNode(
            id=node_id,
            kind="gateway",
            label=label,
            condition_id=cond_id or None,
            action=action,
            target_mode_id=t_mode or None,
            target_track_id=t_track or None,
            target_node_index=t_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": "gateway",
            "label": self.label,
            "action": self.action,
        }
        if self.condition_id:
            out["condition_id"] = self.condition_id
        if self.target_mode_id:
            out["target_mode_id"] = self.target_mode_id
        if self.target_track_id:
            out["target_track_id"] = self.target_track_id
        if self.target_node_index is not None:
            out["target_node_index"] = int(self.target_node_index)
        return out


# ---------- Track / Mode / RotationPreset / RotationsFile ----------

@dataclass
class Track:
    """
    一条轨道：
    - id: 轨道 ID
    - name: 轨道名称（例如 "主循环"、"爆发维护" 等）
    - nodes: 有序节点列表（技能节点 / 网关节点）
    """
    id: str = ""
    name: str = ""
    nodes: List[Node] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Track":
        d = as_dict(d)
        tid = as_str(d.get("id", ""))
        name = as_str(d.get("name", ""))

        nodes_raw = as_list(d.get("nodes", []))
        nodes: List[Node] = []
        for item in nodes_raw:
            if isinstance(item, dict):
                try:
                    node = Node.from_dict(item)
                    nodes.append(node)
                except Exception:
                    # 忽略无法解析的节点
                    pass

        return Track(
            id=tid,
            name=name,
            nodes=nodes,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes],
        }


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
                    pass

        return Mode(
            id=mid,
            name=name,
            tracks=tracks,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tracks": [t.to_dict() for t in self.tracks],
        }


@dataclass
class RotationPreset:
    id: str = ""
    name: str = ""
    description: str = ""

    # 入口配置：executor 将从这里开始运行
    entry_mode_id: str = ""   # 为空表示从全局轨道入口
    entry_track_id: str = ""  # 可为空，表示不指定轨道

    global_tracks: List[Track] = field(default_factory=list)
    modes: List[Mode] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RotationPreset":
        d = as_dict(d)
        pid = as_str(d.get("id", ""))
        name = as_str(d.get("name", ""))
        desc = as_str(d.get("description", ""))
        entry_mode_id = as_str(d.get("entry_mode_id", ""))
        entry_track_id = as_str(d.get("entry_track_id", ""))
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
        )

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
        }


@dataclass
class RotationsFile:
    """
    rotation.json 根对象：
    - schema_version: 版本号，默认 1
    - presets: 多个轨道方案
    """
    schema_version: int = 1
    presets: List[RotationPreset] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RotationsFile":
        d = as_dict(d)
        ver = as_int(d.get("schema_version", 1), 1)

        presets_raw = as_list(d.get("presets", []))
        presets: List[RotationPreset] = []
        for item in presets_raw:
            if isinstance(item, dict):
                try:
                    presets.append(RotationPreset.from_dict(item))
                except Exception:
                    pass

        return RotationsFile(
            schema_version=ver,
            presets=presets,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "presets": [p.to_dict() for p in self.presets],
        }