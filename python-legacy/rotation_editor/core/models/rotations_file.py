from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_list, as_int
from .preset import RotationPreset
from .cycle import CycleConfig

log = logging.getLogger(__name__)


@dataclass
class RotationsFile:
    """
    rotation.json 根对象：

    - schema_version: 版本号，默认 2（v2 新增 cycles）
    - presets: 多个轨道方案（RotationPreset）
    - cycles: 多个循环阶段方案（CycleConfig）
    """
    schema_version: int = 2
    presets: List[RotationPreset] = field(default_factory=list)
    cycles: List[CycleConfig] = field(default_factory=list)

    # ---------- 反序列化 ----------

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
                    log.warning("Failed to parse RotationPreset, skipping", exc_info=True)

        cycles_raw = as_list(d.get("cycles", []))
        cycles: List[CycleConfig] = []
        for item in cycles_raw:
            if isinstance(item, dict):
                try:
                    cycles.append(CycleConfig.from_dict(item))
                except Exception:
                    log.warning("Failed to parse CycleConfig, skipping", exc_info=True)

        return RotationsFile(
            schema_version=max(ver, 2),
            presets=presets,
            cycles=cycles,
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "schema_version": int(self.schema_version),
            "presets": [p.to_dict() for p in self.presets],
        }
        if self.cycles:
            out["cycles"] = [c.to_dict() for c in self.cycles]
        return out