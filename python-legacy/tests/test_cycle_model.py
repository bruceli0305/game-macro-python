"""测试循环阶段模型和执行器。"""

from __future__ import annotations

from rotation_editor.core.models.cycle import SkillSlot, CyclePhase, CycleConfig


def test_skill_slot_from_dict() -> None:
    """SkillSlot 序列化/反序列化。"""
    d = {
        "skill_id": "abc123",
        "priority": 2,
        "label": "火球",
        "condition_expr": {"type": "const", "value": True},
        "override_cast_ms": 500,
    }
    slot = SkillSlot.from_dict(d)
    assert slot.skill_id == "abc123"
    assert slot.priority == 2
    assert slot.label == "火球"
    assert slot.condition_expr is not None
    assert slot.override_cast_ms == 500

    # roundtrip
    d2 = slot.to_dict()
    assert d2["skill_id"] == "abc123"
    assert d2["priority"] == 2
    assert d2["label"] == "火球"


def test_cycle_phase_from_dict() -> None:
    """CyclePhase 序列化/反序列化。"""
    d = {
        "name": "先打AB",
        "skills": [
            {"skill_id": "a", "priority": 1},
            {"skill_id": "b", "priority": 2},
        ],
        "complete_when": "all_fired",
    }
    phase = CyclePhase.from_dict(d)
    assert phase.name == "先打AB"
    assert len(phase.skills) == 2
    assert phase.skills[0].skill_id == "a"  # priority 1 排在前面
    assert phase.skills[1].skill_id == "b"
    assert phase.complete_when == "all_fired"


def test_cycle_config_from_dict() -> None:
    """CycleConfig 序列化/反序列化。"""
    d = {
        "name": "测试循环",
        "phases": [
            {"name": "P1", "skills": [{"skill_id": "a", "priority": 1}], "complete_when": "all_fired"},
            {"name": "P2", "skills": [{"skill_id": "b", "priority": 1}], "complete_when": "all_fired"},
        ],
        "poll_interval_ms": 100,
        "max_cycles": 5,
    }
    cfg = CycleConfig.from_dict(d)
    assert cfg.name == "测试循环"
    assert len(cfg.phases) == 2
    assert cfg.phases[0].name == "P1"
    assert cfg.phases[1].name == "P2"
    assert cfg.poll_interval_ms == 100
    assert cfg.max_cycles == 5

    # roundtrip
    d2 = cfg.to_dict()
    assert d2["name"] == "测试循环"
    assert len(d2["phases"]) == 2


def test_cycle_config_from_template() -> None:
    """从模板创建 CycleConfig。"""
    from rotation_editor.core.templates import create_cycle_priority

    cfg = create_cycle_priority("测试")
    assert cfg.name == "测试"
    assert len(cfg.phases) == 3

    # Phase 1: 先打AB
    p1 = cfg.phases[0]
    assert p1.name == "先打A和B"
    assert len(p1.skills) == 2
    assert p1.skills[0].priority == 1  # A 优先
    assert p1.skills[1].priority == 2  # B 次优先
    assert p1.complete_when == "all_fired"

    # Phase 2: 放D
    p2 = cfg.phases[1]
    assert len(p2.skills) == 1
    assert p2.complete_when == "all_fired"

    # Phase 3: 放C
    p3 = cfg.phases[2]
    assert len(p3.skills) == 1
    assert p3.complete_when == "all_fired"


def test_rotations_file_includes_cycles() -> None:
    """RotationsFile 应该能序列化/反序列化 cycles。"""
    from rotation_editor.core.models import RotationsFile, CycleConfig, CyclePhase, SkillSlot

    rf = RotationsFile()
    rf.cycles.append(CycleConfig(
        name="测试循环",
        phases=[
            CyclePhase(name="P1", skills=[SkillSlot(skill_id="a", priority=1)]),
        ],
    ))

    d = rf.to_dict()
    assert "cycles" in d
    assert len(d["cycles"]) == 1
    assert d["cycles"][0]["name"] == "测试循环"

    # roundtrip
    rf2 = RotationsFile.from_dict(d)
    assert len(rf2.cycles) == 1
    assert rf2.cycles[0].name == "测试循环"
    assert rf2.cycles[0].phases[0].skills[0].skill_id == "a"
