# tests/test_condition_eval.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from core.models.point import Point, PointsFile
from core.models.skill import Skill, SkillsFile, ColorRGB
from rotation_editor.core.models import Condition
from rotation_editor.core.runtime.context import RuntimeContext
from rotation_editor.core.runtime.condition_eval import eval_condition
from core.pick.capture import SampleSpec
from core.profiles import ProfileContext
from core.domain.profile import Profile


@dataclass
class DummyCapture:
    """只返回固定颜色的假 ScreenCapture 替身。"""
    r: int
    g: int
    b: int

    def get_rgb_scoped_abs(self, x_abs, y_abs, sample, monitor_key, *, require_inside=True):
        return self.r, self.g, self.b


def make_profile_with_point_and_skill() -> Profile:
    # 构造 profile，带一个点位和一个技能像素
    p = Profile()
    pt = Point(
        id="pt1",
        name="P1",
        monitor="primary",
        vx=0,
        vy=0,
        color=ColorRGB(100, 150, 200),
        tolerance=0,
        captured_at="",
    )
    p.points = PointsFile(points=[pt])

    sk = Skill(id="sk1", name="S1", enabled=True)
    sk.pixel.monitor = "primary"
    sk.pixel.vx = 0
    sk.pixel.vy = 0
    sk.pixel.color = ColorRGB(50, 60, 70)
    p.skills = SkillsFile(skills=[sk])

    return p


class DummyCtx(ProfileContext):
    """只为了 RuntimeContext.profile 类型匹配，实际不会用到 ProfileContext 的其它字段。"""
    pass  # 在测试中不会真正调用 ProfileContext 的方法


def make_runtime_context(rgb=(100, 150, 200)) -> RuntimeContext:
    prof = make_profile_with_point_and_skill()
    # 构造一个假的 ProfileContext，只挂 profile
    dummy = object.__new__(ProfileContext)
    dummy.profile = prof  # type: ignore[attr-defined]
    cap = DummyCapture(*rgb)
    return RuntimeContext(profile=dummy, capture=cap)  # type: ignore[arg-type]


def test_logic_and_or_not() -> None:
    ctx = make_runtime_context()

    # 子节点全部为 False
    cond_false = Condition(
        id="c1",
        name="c1",
        kind="expr_tree_v1",
        expr={
            "type": "logic_and",
            "children": [
                {"type": "pixel_point", "point_id": "non_exist", "tolerance": 10},
                {"type": "pixel_skill", "skill_id": "non_exist", "tolerance": 10},
            ],
        },
    )
    assert eval_condition(cond_false, ctx) is False

    cond_or = Condition(
        id="c2",
        name="c2",
        kind="expr_tree_v1",
        expr={
            "type": "logic_or",
            "children": [
                {"type": "pixel_point", "point_id": "non_exist", "tolerance": 10},
                {"type": "pixel_point", "point_id": "pt1", "tolerance": 10},
            ],
        },
    )
    # 模拟点位 pt1 颜色匹配 => runtime context 已设置相同颜色
    assert eval_condition(cond_or, ctx) is True

    cond_not = Condition(
        id="c3",
        name="c3",
        kind="expr_tree_v1",
        expr={
            "type": "logic_not",
            "child": {"type": "pixel_point", "point_id": "pt1", "tolerance": 0},
        },
    )
    # 颜色完全相同，tolerance=0 => 内部应为 True，not True => False
    assert eval_condition(cond_not, ctx) is False


def test_pixel_point_tolerance() -> None:
    # pt1 颜色是 (100,150,200)
    ctx_match = make_runtime_context(rgb=(100, 150, 200))
    ctx_miss = make_runtime_context(rgb=(130, 150, 200))

    cond = Condition(
        id="cp",
        name="cp",
        kind="expr_tree_v1",
        expr={
            "type": "pixel_point",
            "point_id": "pt1",
            "tolerance": 20,
        },
    )

    assert eval_condition(cond, ctx_match) is True
    # 最大通道差为 30 > 20 => False
    assert eval_condition(cond, ctx_miss) is False


def test_pixel_skill_tolerance() -> None:
    # sk1 像素颜色 (50,60,70)
    ctx_match = make_runtime_context(rgb=(50, 60, 70))
    ctx_miss = make_runtime_context(rgb=(80, 60, 70))

    cond = Condition(
        id="cs",
        name="cs",
        kind="expr_tree_v1",
        expr={
            "type": "pixel_skill",
            "skill_id": "sk1",
            "tolerance": 20,
        },
    )

    assert eval_condition(cond, ctx_match) is True
    # 最大通道差为 30 > 20 => False
    assert eval_condition(cond, ctx_miss) is False