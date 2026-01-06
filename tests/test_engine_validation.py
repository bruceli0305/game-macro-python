from __future__ import annotations

from typing import Callable, List, Tuple

from rotation_editor.core.models import RotationPreset, EntryPoint
from rotation_editor.core.runtime import MacroEngine
from core.models.skill import SkillsFile
from core.models.point import PointsFile


class DummyScheduler:
    """
    简单的调度器替身：
    - 记录传入的回调，并立即执行（同步）
    """
    def __init__(self) -> None:
        self.calls: List[Callable[[], None]] = []

    def call_soon(self, fn: Callable[[], None]) -> None:
        self.calls.append(fn)
        fn()  # 测试中直接同步执行，便于断言回调效果


class DummyCallbacks:
    """
    实现 EngineCallbacks 协议的测试替身：
    - 记录 on_error / on_started / on_stopped 的调用情况
    """
    def __init__(self) -> None:
        self.started: List[str] = []
        self.stopped: List[str] = []
        self.errors: List[Tuple[str, str]] = []
        self.nodes: List[Tuple[object, object]] = []

    def on_started(self, preset_id: str) -> None:
        self.started.append(preset_id)

    def on_stopped(self, reason: str) -> None:
        self.stopped.append(reason)

    def on_error(self, msg: str, detail: str) -> None:
        self.errors.append((msg, detail))

    def on_node_executed(self, cursor, node) -> None:
        self.nodes.append((cursor, node))


class DummyCtx:
    """
    只提供 .skills/.points 属性，供 ValidationService/AST 使用。
    实际上 MacroEngine 在预校验失败时，不会真正用到 capture/metrics。
    """
    def __init__(self) -> None:
        self.skills = SkillsFile(skills=[])
        self.points = PointsFile(points=[])


def test_engine_start_with_invalid_entry_reports_error_and_does_not_run() -> None:
    """
    当 RotationPreset.entry 非法（track/node 不合法）时：
    - MacroEngine.start 不应启动引擎线程；
    - 应通过 callbacks.on_error 报告“循环方案校验失败”；
    - is_running() 应返回 False。
    """
    # 构造一个 entry 明显非法的 preset：track_id/node_id 都为空
    preset = RotationPreset(
        id="ptest",
        name="PresetTest",
        description="",
        entry=EntryPoint(
            scope="global",
            mode_id="",
            track_id="",
            node_id="",  # 非法入口：缺少轨道与节点
        ),
    )

    ctx = DummyCtx()
    scheduler = DummyScheduler()
    cb = DummyCallbacks()

    eng = MacroEngine(
        ctx=ctx,            # DummyCtx，仅满足接口
        scheduler=scheduler,
        callbacks=cb,
    )

    # 调用 start，应当只触发 on_error，而不进入运行状态
    eng.start(preset)

    # 引擎线程不应启动
    assert not eng.is_running(), "预期引擎在入口校验失败时不会进入运行状态"

    # 不应有 on_started/on_stopped
    assert cb.started == [], f"不应调用 on_started，但实际: {cb.started}"
    assert cb.stopped == [], f"不应调用 on_stopped，但实际: {cb.stopped}"

    # 应有一次 on_error 调用
    assert len(cb.errors) == 1, f"预期 callbacks.on_error 被调用一次，实际为 {len(cb.errors)} 次"

    msg, detail = cb.errors[0]
    assert "循环方案校验失败" in msg, f"错误提示信息不符合预期: {msg!r}"
    # detail 文本由 ValidationService.format_text 生成，这里只检查非空即可
    assert detail.strip(), "预期错误详情非空（应包含 ValidationReport）"