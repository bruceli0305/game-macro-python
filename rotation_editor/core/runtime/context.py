from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.profiles import ProfileContext
from core.pick.capture import ScreenCapture

from .skill_state import SkillState


@dataclass
class RuntimeContext:
    """
    条件评估运行时上下文：

    - profile: 当前 ProfileContext（包含 skills/points/rotations 等数据）
    - capture: 屏幕取色器，用于像素条件（点位/技能像素）的实时采样
    - skill_state: 技能状态机接口（可选，当前阶段可以为 None）

    未来执行引擎在实际跑循环时会构造 RuntimeContext，并传给条件评估器。
    """

    profile: ProfileContext
    capture: ScreenCapture
    skill_state: Optional[SkillState] = None