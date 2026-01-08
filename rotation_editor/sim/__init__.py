# rotation_editor/sim/__init__.py
from __future__ import annotations

"""
rotation_editor.sim

循环方案离线推演（Simulation）核心模块：
- models: 推演过程中使用的数据结构（SimEvent / SimResult 等）
- simulator: RotationSimulator 主类（根据 ProfileContext + RotationPreset 生成推演结果）

注意：本模块不依赖 Qt，仅依赖 core.profiles / rotation_editor.core.models /
      rotation_editor.core.runtime.runtime_state / scheduler 等，可以在单元测试或
      非 GUI 环境中单独使用。
"""

from .models import SkillSimState, SimEvent, SimConfig, SimResult
from .simulator import RotationSimulator

__all__ = [
    "SkillSimState",
    "SimEvent",
    "SimConfig",
    "SimResult",
    "RotationSimulator",
]