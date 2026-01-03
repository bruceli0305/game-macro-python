from __future__ import annotations

"""
rotation_editor.core

核心领域模型与存储接口的统一出口：
- 数据模型：Condition / Node / SkillNode / GatewayNode / Track / Mode / RotationPreset / RotationsFile
- 存储：load_or_create_rotations / save_rotations

注意：
- 服务层（RotationService）在 rotation_editor.core.services.rotation_service 中，
  为避免循环依赖，不在此处导入。
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
from .storage import load_or_create_rotations, save_rotations

__all__ = [
    "Condition",
    "Node",
    "SkillNode",
    "GatewayNode",
    "Track",
    "Mode",
    "RotationPreset",
    "RotationsFile",
    "load_or_create_rotations",
    "save_rotations",
]