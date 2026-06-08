"""
rotation_editor.core.models.cycle — 循环阶段执行模型。

核心概念：
- CyclePhase: 一个执行阶段，包含若干按优先级排序的候选技能
- SkillSlot: 单个候选技能槽位（技能ID + 优先级 + 可选条件）
- CycleConfig: 完整的循环配置（阶段列表 + 全局设置）

执行语义：
- 引擎在当前 Phase 中，按优先级从高到低检查候选技能
- 执行第一个"就绪"的技能（CD好了 + 条件满足）
- Phase 完成条件满足后，推进到下一个 Phase
- 所有 Phase 完成后，循环重置

典型场景：
  Phase 1: [A(pri=1), B(pri=2)]  → "先打A，A没好就打B"
  Phase 2: [D(pri=1)]            → "AB都放过且C没放过 → 放D"
  Phase 3: [C(pri=1)]            → "ABD都放过 → 放C"
  → 循环重置
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.models.common import as_dict, as_list, as_str, as_int, as_bool

log = logging.getLogger(__name__)


@dataclass
class SkillSlot:
    """
    候选技能槽位。

    - skill_id: 引用 SkillsFile.skills[].id
    - priority: 优先级（数值越小越优先，1 = 最高）
    - label: 显示标签（可选，默认用技能名称）
    - condition_expr: 可选的 AST JSON 条件（如像素匹配/技能指标）
                     为空时仅检查 CD 就绪
    - override_cast_ms: 覆盖读条时间（可选）
    """
    skill_id: str = ""
    priority: int = 1
    label: str = ""
    condition_expr: Optional[Dict[str, Any]] = None
    override_cast_ms: Optional[int] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SkillSlot":
        d = as_dict(d)
        ce = d.get("condition_expr", None)
        return SkillSlot(
            skill_id=as_str(d.get("skill_id", "")),
            priority=as_int(d.get("priority", 1), 1),
            label=as_str(d.get("label", "")),
            condition_expr=dict(ce) if isinstance(ce, dict) and ce else None,
            override_cast_ms=as_int(d.get("override_cast_ms", 0), 0) or None,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "skill_id": self.skill_id,
            "priority": int(self.priority),
        }
        if self.label:
            out["label"] = self.label
        if isinstance(self.condition_expr, dict) and self.condition_expr:
            out["condition_expr"] = dict(self.condition_expr)
        if self.override_cast_ms is not None:
            out["override_cast_ms"] = int(self.override_cast_ms)
        return out


@dataclass
class CyclePhase:
    """
    循环阶段。

    - name: 阶段名称（如"先打AB"）
    - skills: 候选技能列表（按 priority 排序）
    - complete_when: 完成条件
        * "all_fired" — 所有候选技能都至少释放过一次
        * "any_fired" — 任一候选技能释放过一次
        * "always"    — 执行一个技能后立即完成
    """
    name: str = ""
    skills: List[SkillSlot] = field(default_factory=list)
    complete_when: str = "all_fired"  # "all_fired" | "any_fired" | "always"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CyclePhase":
        d = as_dict(d)
        skills_raw = as_list(d.get("skills", []))
        skills: List[SkillSlot] = []
        for item in skills_raw:
            if isinstance(item, dict):
                try:
                    skills.append(SkillSlot.from_dict(item))
                except Exception:
                    log.warning("Failed to parse SkillSlot, skipping", exc_info=True)
        # 按 priority 排序
        skills.sort(key=lambda s: s.priority)
        return CyclePhase(
            name=as_str(d.get("name", "")),
            skills=skills,
            complete_when=as_str(d.get("complete_when", "all_fired"), "all_fired"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "skills": [s.to_dict() for s in self.skills],
            "complete_when": self.complete_when,
        }


@dataclass
class CycleConfig:
    """
    完整的循环阶段配置。

    - name: 配置名称
    - phases: 阶段列表（按顺序执行）
    - poll_interval_ms: 检查间隔（毫秒）
    - max_cycles: 最大循环次数（0=无限）
    """
    name: str = ""
    phases: List[CyclePhase] = field(default_factory=list)
    poll_interval_ms: int = 50
    max_cycles: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CycleConfig":
        d = as_dict(d)
        phases_raw = as_list(d.get("phases", []))
        phases: List[CyclePhase] = []
        for item in phases_raw:
            if isinstance(item, dict):
                try:
                    phases.append(CyclePhase.from_dict(item))
                except Exception:
                    log.warning("Failed to parse CyclePhase, skipping", exc_info=True)
        return CycleConfig(
            name=as_str(d.get("name", "")),
            phases=phases,
            poll_interval_ms=as_int(d.get("poll_interval_ms", 50), 50),
            max_cycles=as_int(d.get("max_cycles", 0), 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phases": [p.to_dict() for p in self.phases],
            "poll_interval_ms": int(self.poll_interval_ms),
            "max_cycles": int(self.max_cycles),
        }
