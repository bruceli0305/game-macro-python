# rotation_editor/core/models/entry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from core.models.common import as_dict, as_str


@dataclass
class EntryPoint:
    """
    入口点（新结构，后续引擎会严格使用它）：

    - scope: "global" | "mode"
    - mode_id: scope=="mode" 时必填
    - track_id: 必填
    - node_id: 必填（后续会要求；当前阶段 UI 仍只维护旧 entry_mode_id/entry_track_id，
              因此 node_id 可能为空，后续步骤会补齐并移除旧字段）
    """
    scope: str = "global"
    mode_id: str = ""
    track_id: str = ""
    node_id: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "EntryPoint":
        d = as_dict(d)
        scope = as_str(d.get("scope", "global"), "global").strip().lower() or "global"
        if scope not in ("global", "mode"):
            scope = "global"

        mode_id = as_str(d.get("mode_id", ""))
        track_id = as_str(d.get("track_id", ""))
        node_id = as_str(d.get("node_id", ""))

        # 宽松兜底：scope=mode 但 mode_id 为空时，不强制改 scope；校验交给后续 ValidationService。
        return EntryPoint(
            scope=scope,
            mode_id=mode_id,
            track_id=track_id,
            node_id=node_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": (self.scope or "global").strip().lower() or "global",
            "mode_id": (self.mode_id or "").strip(),
            "track_id": (self.track_id or "").strip(),
            "node_id": (self.node_id or "").strip(),
        }