from __future__ import annotations

from typing import Set

from rotation_editor.core.models import RotationPreset, Track, Node, EntryPoint
from rotation_editor.core.services.validation_service import ValidationService


def _entry_error_codes(report) -> Set[str]:
    """从 ValidationReport 中提取所有 entry.* 相关错误 code。"""
    return {
        d.code
        for d in (report.diagnostics or [])
        if d.level == "error" and d.code.startswith("entry.")
    }


def test_entry_valid_global_track_and_node() -> None:
    """
    entry 指向一个存在的全局轨道和该轨道内的节点时，不应有 entry.* 错误。
    """
    # 构造一个只有全局轨道的 preset
    preset = RotationPreset(
        id="p1",
        name="P1",
        description="",
    )

    # 全局轨道 t1，包含一个 Node(id=n1)
    track = Track(
        id="t1",
        name="G1",
        nodes=[Node(id="n1", kind="other", label="N1")],
    )
    preset.global_tracks.append(track)

    # 入口：global -> track t1, node n1
    preset.entry = EntryPoint(
        scope="global",
        mode_id="",
        track_id="t1",
        node_id="n1",
    )

    vs = ValidationService()
    report = vs.validate_preset(preset, ctx=None)

    codes = _entry_error_codes(report)
    assert not codes, f"不应有 entry.* 错误，但实际为: {codes}"


def test_entry_track_missing() -> None:
    """
    entry.track_id 指向不存在的轨道时，应报 entry.track.missing。
    """
    preset = RotationPreset(
        id="p2",
        name="P2",
        description="",
    )

    # 仍然只有全局轨道 t1
    track = Track(
        id="t1",
        name="G1",
        nodes=[Node(id="n1", kind="other", label="N1")],
    )
    preset.global_tracks.append(track)

    # 入口 track_id 设置为不存在的 "bad"
    preset.entry = EntryPoint(
        scope="global",
        mode_id="",
        track_id="bad",
        node_id="n1",
    )

    vs = ValidationService()
    report = vs.validate_preset(preset, ctx=None)

    codes = _entry_error_codes(report)
    assert "entry.track.missing" in codes


def test_entry_node_missing_in_track() -> None:
    """
    entry.node_id 不属于指定轨道时，应报 entry.node.missing。
    """
    preset = RotationPreset(
        id="p3",
        name="P3",
        description="",
    )

    # 全局轨道 t1 上只有节点 n1
    track = Track(
        id="t1",
        name="G1",
        nodes=[Node(id="n1", kind="other", label="N1")],
    )
    preset.global_tracks.append(track)

    # 入口 node_id 设置为不存在的 "bad"
    preset.entry = EntryPoint(
        scope="global",
        mode_id="",
        track_id="t1",
        node_id="bad",
    )

    vs = ValidationService()
    report = vs.validate_preset(preset, ctx=None)

    codes = _entry_error_codes(report)
    assert "entry.node.missing" in codes