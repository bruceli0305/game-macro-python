from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_dict, as_list, as_int
from .preset import RotationPreset


@dataclass
class RotationsFile:
    """
    rotation.json 根对象：

    - schema_version: 版本号，默认 1
    - presets: 多个轨道方案（RotationPreset）
    """
    schema_version: int = 1
    presets: List[RotationPreset] = field(default_factory=list)

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
                    pass

        return RotationsFile(
            schema_version=ver,
            presets=presets,
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "presets": [p.to_dict() for p in self.presets],
        }