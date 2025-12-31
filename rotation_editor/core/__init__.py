# rotation_editor/core/__init__.py
"""
Core data & storage for rotation editor.

注意：这里不要 import services，否则会引发与 core.profiles/core.store.app_store 的循环导入。
服务层请显式从 rotation_editor.core.services import RotationService 导入。
"""

from .models import (
    RotationsFile,
    RotationPreset,
    Mode,
    Track,
    Node,
    SkillNode,
    GatewayNode,
    Condition,
)
from .storage import load_or_create_rotations, save_rotations

__all__ = [
    "RotationsFile",
    "RotationPreset",
    "Mode",
    "Track",
    "Node",
    "SkillNode",
    "GatewayNode",
    "Condition",
    "load_or_create_rotations",
    "save_rotations",
]