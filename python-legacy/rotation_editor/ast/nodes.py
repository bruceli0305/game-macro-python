from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple, Union


# ----------- Bool core -----------

@dataclass(frozen=True)
class And:
    children: Tuple["Expr", ...]


@dataclass(frozen=True)
class Or:
    children: Tuple["Expr", ...]


@dataclass(frozen=True)
class Not:
    child: "Expr"


@dataclass(frozen=True)
class Const:
    value: bool


# ----------- Atoms -----------

@dataclass(frozen=True)
class PixelMatchPoint:
    point_id: str
    tolerance: int  # 0..255


@dataclass(frozen=True)
class PixelMatchSkill:
    skill_id: str
    tolerance: int  # 0..255


@dataclass(frozen=True)
class CastBarChanged:
    """
    开始施法信号常用：施法条采样点与 baseline 相比发生变化。
    baseline 的采集由执行器/状态机负责；AST 只表达“我要这个信号”。
    """
    point_id: str
    tolerance: int  # 0..255


SkillMetric = Literal["success", "attempt_started", "key_sent_ok", "cast_started", "fail"]


@dataclass(frozen=True)
class SkillMetricGE:
    skill_id: str
    metric: SkillMetric
    count: int  # >=1


Expr = Union[
    And,
    Or,
    Not,
    Const,
    PixelMatchPoint,
    PixelMatchSkill,
    CastBarChanged,
    SkillMetricGE,
]