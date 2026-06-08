# tests/test_condition_eval.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest

from core.models.point import Point, PointsFile
from core.models.skill import Skill, SkillsFile, ColorRGB

from rotation_editor.ast import (
    decode_expr,
    evaluate,
    EvalContext,
    TriBool,
)


RGB = Tuple[int, int, int]


@dataclass
class DummySampler:
    """
    简单的 PixelSampler 替身：
    - 无论坐标/monitor/sample 为何，都返回固定的 RGB
    """
    r: int
    g: int
    b: int

    def sample_rgb_abs(
        self,
        *,
        monitor_key: str,
        x_abs: int,
        y_abs: int,
        sample,
        require_inside: bool = False,
    ) -> Optional[RGB]:
        return int(self.r), int(self.g), int(self.b)


@dataclass
class DummyProfile:
    """
    只提供 .points.points / .skills.skills 两个属性，
    供 AST evaluator 使用。
    """
    points: PointsFile
    skills: SkillsFile


def make_profile_with_point_and_skill() -> DummyProfile:
    """
    构造一个 profile，带一个点位和一个技能像素：
    - point id="pt1", color=(100,150,200)
    - skill id="sk1", pixel.color=(50,60,70)
    """
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
    points = PointsFile(points=[pt])

    sk = Skill(id="sk1", name="S1", enabled=True)
    sk.pixel.monitor = "primary"
    sk.pixel.vx = 0
    sk.pixel.vy = 0
    sk.pixel.color = ColorRGB(50, 60, 70)
    skills = SkillsFile(skills=[sk])

    return DummyProfile(points=points, skills=skills)


def make_eval_ctx(rgb: RGB) -> EvalContext:
    """
    构造 EvalContext：
    - profile: DummyProfile（只要 .points/.skills）
    - sampler: DummySampler（返回固定 RGB）
    - metrics/baseline 暂不使用
    """
    prof = make_profile_with_point_and_skill()
    sampler = DummySampler(*rgb)
    # EvalContext.profile 类型标注是 ProfileContext，这里传 DummyProfile 也可工作
    return EvalContext(profile=prof, sampler=sampler)  # type: ignore[arg-type]


def tri_is_true(v: TriBool) -> bool:
    return v.value is True


def tri_is_false(v: TriBool) -> bool:
    return v.value is False


def test_logic_and_or_not() -> None:
    """
    纯逻辑节点（const/and/or/not）的求值：
    - AND: 任一 False -> False
    - OR : 任一 True  -> True
    - NOT: 取反
    """
    ctx = make_eval_ctx((0, 0, 0))  # sampler 在本测试中不会真正用到

    # (False AND True) -> False
    expr_json_and = {
        "type": "and",
        "children": [
            {"type": "const", "value": False},
            {"type": "const", "value": True},
        ],
    }
    expr_and, diags_and = decode_expr(expr_json_and)
    assert expr_and is not None
    assert not any(d.is_error() for d in diags_and)
    r_and = evaluate(expr_and, ctx)
    assert tri_is_false(r_and)

    # (False OR True) -> True
    expr_json_or = {
        "type": "or",
        "children": [
            {"type": "const", "value": False},
            {"type": "const", "value": True},
        ],
    }
    expr_or, diags_or = decode_expr(expr_json_or)
    assert expr_or is not None
    assert not any(d.is_error() for d in diags_or)
    r_or = evaluate(expr_or, ctx)
    assert tri_is_true(r_or)

    # NOT(True) -> False
    expr_json_not = {
        "type": "not",
        "child": {"type": "const", "value": True},
    }
    expr_not, diags_not = decode_expr(expr_json_not)
    assert expr_not is not None
    assert not any(d.is_error() for d in diags_not)
    r_not = evaluate(expr_not, ctx)
    assert tri_is_false(r_not)


def test_pixel_point_tolerance() -> None:
    """
    PixelMatchPoint 容差测试：
    - 点位 pt1 颜色 (100,150,200)
    - 当前采样 rgb=(100,150,200) 时，tolerance=20 应该匹配
    - 当前采样 rgb=(130,150,200) 时，最大通道差=30>20，应判定为 False
    """
    # 颜色匹配
    ctx_match = make_eval_ctx((100, 150, 200))
    # 颜色不匹配（R 差 30）
    ctx_miss = make_eval_ctx((130, 150, 200))

    expr_json = {
        "type": "pixel_point",
        "point_id": "pt1",
        "tolerance": 20,
    }
    expr, diags = decode_expr(expr_json)
    assert expr is not None
    assert not any(d.is_error() for d in diags)

    r_match = evaluate(expr, ctx_match)
    assert tri_is_true(r_match)

    r_miss = evaluate(expr, ctx_miss)
    # 最大通道差 30 > 20 -> False
    assert tri_is_false(r_miss)


def test_pixel_skill_tolerance() -> None:
    """
    PixelMatchSkill 容差测试：
    - 技能 sk1 像素颜色 (50,60,70)
    - 当前采样 rgb=(50,60,70) 时，tolerance=20 应该匹配
    - 当前采样 rgb=(80,60,70) 时，最大通道差=30>20，应判定为 False
    """
    ctx_match = make_eval_ctx((50, 60, 70))
    ctx_miss = make_eval_ctx((80, 60, 70))

    expr_json = {
        "type": "pixel_skill",
        "skill_id": "sk1",
        "tolerance": 20,
    }
    expr, diags = decode_expr(expr_json)
    assert expr is not None
    assert not any(d.is_error() for d in diags)

    r_match = evaluate(expr, ctx_match)
    assert tri_is_true(r_match)

    r_miss = evaluate(expr, ctx_miss)
    assert tri_is_false(r_miss)