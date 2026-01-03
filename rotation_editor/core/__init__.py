from __future__ import annotations

"""
rotation_editor.core

核心领域模型的统一出口：
- 数据模型：
    * Condition
    * Node / SkillNode / GatewayNode
    * Track
    * Mode
    * RotationPreset
    * RotationsFile

说明：
- 原先这里还暴露了 load_or_create_rotations / save_rotations（来自 core.storage），
  现在已改为统一由 ProfileSession + ProfileRepository 读写 profile.json，
  不再有独立的 rotation.json 存储模块。
"""

from .models import (
    Condition,
    Node,
    SkillNode,
    GatewayNode,
    Track,
    Mode,
    RotationPreset,
    RotationsFile,
)

__all__ = [
    "Condition",
    "Node",
    "SkillNode",
    "GatewayNode",
    "Track",
    "Mode",
    "RotationPreset",
    "RotationsFile",
]