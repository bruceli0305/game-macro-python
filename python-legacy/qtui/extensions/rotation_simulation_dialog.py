from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QSplitter,
)

from core.profiles import ProfileContext
from rotation_editor.sim import RotationSimulator, SimConfig, SimEvent
from rotation_editor.core.models import RotationPreset
from rotation_editor.core.services.rotation_service import RotationService

from qtui.extensions.sim_timeline_view import SimulationTimelineView


class RotationSimulationDialog(QDialog):
    """
    循环推演结果查看器：

    功能：
    - 选择一个 RotationPreset；
    - 设置最大模拟时长(秒) / 最大节点数；
    - 调用 RotationSimulator.run() 获得 SimResult；
    - 上半部分：SimulationTimelineView 时间轴视图（矩形块，可缩放）；
    - 下半部分：QTableWidget 事件列表；
    - 双击表格行或点击时间轴块弹出事件详情。

    展示策略：
    - 只展示“真正生效”的事件：
        * SkillNode: 只看 outcome="SUCCESS"
        * GatewayNode: 只看 GW_END / GW_EXEC_* / GW_JUMP_* / GW_TAKEN 等
        * 过滤掉：SKIPPED_CD / SKIPPED_NOT_READY / GW_COND_FALSE 等“未触发/未释放”的事件
    """

    def __init__(
        self,
        *,
        parent,
        ctx: ProfileContext,
        rotation_service: RotationService,
    ) -> None:
        super().__init__(parent)

        self._ctx = ctx
        self._svc = rotation_service

        self.setWindowTitle("循环推演结果查看器")
        self.resize(1100, 640)

        # 原始 events（未经过滤的完整推演事件）
        self._events_all: List[SimEvent] = []
        # 当前展示用（已过滤）的事件
        self._events_visible: List[SimEvent] = []

        self._build_ui()
        self._reload_presets()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 顶部：preset 选择 + 刷新
        row_top = QHBoxLayout()
        row_top.addWidget(QLabel("方案(Preset):", self))

        self._cmb_preset = QComboBox(self)
        row_top.addWidget(self._cmb_preset, 1)

        btn_refresh = QPushButton("刷新", self)
        btn_refresh.clicked.connect(self._reload_presets)
        row_top.addWidget(btn_refresh)

        layout.addLayout(row_top)

        # 推演配置：最长时长 / 最大节点数
        row_cfg = QHBoxLayout()

        row_cfg.addWidget(QLabel("最长模拟时长(秒,0=默认):", self))
        self._spin_max_secs = QSpinBox(self)
        self._spin_max_secs.setRange(0, 10**7)
        self._spin_max_secs.setSingleStep(10)
        self._spin_max_secs.setValue(120)
        row_cfg.addWidget(self._spin_max_secs)

        row_cfg.addSpacing(12)

        row_cfg.addWidget(QLabel("最大节点数(0=默认):", self))
        self._spin_max_nodes = QSpinBox(self)
        self._spin_max_nodes.setRange(0, 10**7)
        self._spin_max_nodes.setSingleStep(100)
        self._spin_max_nodes.setValue(500)
        row_cfg.addWidget(self._spin_max_nodes)

        row_cfg.addStretch(1)
        layout.addLayout(row_cfg)

        # 按钮行：开始推演 / 关闭
        row_btn = QHBoxLayout()
        row_btn.addStretch(1)

        self._btn_run = QPushButton("开始推演", self)
        self._btn_run.clicked.connect(self._on_run_clicked)
        row_btn.addWidget(self._btn_run)

        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.close)
        row_btn.addWidget(btn_close)

        layout.addLayout(row_btn)

        # 结果标签
        self._lbl_summary = QLabel("尚未推演。", self)
        layout.addWidget(self._lbl_summary)

        # 时间轴缩放控件
        row_zoom = QHBoxLayout()
        row_zoom.addWidget(QLabel("时间轴缩放:", self))

        self._btn_zoom_out = QPushButton("-", self)
        self._btn_zoom_out.setFixedWidth(26)
        self._btn_zoom_out.clicked.connect(self._on_zoom_out_clicked)
        row_zoom.addWidget(self._btn_zoom_out)

        self._lbl_zoom = QLabel("100%", self)
        self._lbl_zoom.setFixedWidth(48)
        self._lbl_zoom.setAlignment(Qt.AlignCenter)
        row_zoom.addWidget(self._lbl_zoom)

        self._btn_zoom_in = QPushButton("+", self)
        self._btn_zoom_in.setFixedWidth(26)
        self._btn_zoom_in.clicked.connect(self._on_zoom_in_clicked)
        row_zoom.addWidget(self._btn_zoom_in)

        self._btn_zoom_reset = QPushButton("1x", self)
        self._btn_zoom_reset.setFixedWidth(32)
        self._btn_zoom_reset.clicked.connect(self._on_zoom_reset_clicked)
        row_zoom.addWidget(self._btn_zoom_reset)

        row_zoom.addStretch(1)
        layout.addLayout(row_zoom)

        # 中部：Splitter，顶部时间轴，底部表格
        splitter = QSplitter(Qt.Vertical, self)
        splitter.setChildrenCollapsible(False)

        # 时间轴视图
        self._timeline = SimulationTimelineView(self)
        self._timeline.eventClicked.connect(self._on_timeline_event_clicked)
        splitter.addWidget(self._timeline)

        # 事件表格
        self._table = QTableWidget(self)
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "#",
            "时间ms",
            "时间s",
            "scope",
            "mode_id(后6)",
            "track_id(后6)",
            "节点标签",
            "类型",
            "结果",
            "原因",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        splitter.addWidget(self._table)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

    # ---------- preset 列表 ----------

    def _reload_presets(self) -> None:
        presets = self._svc.list_presets()
        self._cmb_preset.blockSignals(True)
        self._cmb_preset.clear()
        for p in presets:
            pid = getattr(p, "id", "") or ""
            name = getattr(p, "name", "") or "(未命名)"
            self._cmb_preset.addItem(name, userData=pid)
        self._cmb_preset.blockSignals(False)

        if self._cmb_preset.count() > 0:
            self._cmb_preset.setCurrentIndex(0)

    def _current_preset(self) -> Optional[RotationPreset]:
        idx = self._cmb_preset.currentIndex()
        if idx < 0:
            return None
        pid = self._cmb_preset.currentData()
        if not isinstance(pid, str):
            return None
        pid_s = (pid or "").strip()
        if not pid_s:
            return None
        return self._svc.find_preset(pid_s)

    # ---------- 推演执行 ----------

    def _on_run_clicked(self) -> None:
        preset = self._current_preset()
        if preset is None:
            QMessageBox.information(self, "提示", "当前没有可用的循环方案(Preset)。", QMessageBox.Ok)
            return

        # 配置 SimConfig
        secs = int(self._spin_max_secs.value())
        nodes = int(self._spin_max_nodes.value())

        max_run_ms = secs * 1000 if secs > 0 else 0
        max_nodes = nodes if nodes > 0 else 0

        cfg = SimConfig(
            max_run_ms=max_run_ms or 120_000,
            max_exec_nodes=max_nodes or 500,
        )

        sim = RotationSimulator(ctx=self._ctx, preset=preset, cfg=cfg)

        try:
            result = sim.run()
        except Exception as e:
            QMessageBox.critical(self, "推演失败", f"推演过程中发生异常：\n{e}", QMessageBox.Ok)
            return

        # 存完整 events
        self._events_all = list(result.events or [])

        # 过滤出“可释放 / 真正生效”的事件
        visible = [e for e in self._events_all if not self._is_ignored_for_view(e)]
        self._events_visible = visible

        self._populate_table(self._events_visible, result)

    # ---------- 过滤规则 ----------

    def _is_ignored_for_view(self, ev: SimEvent) -> bool:
        """
        判断某个事���是否在视图中隐藏：
        - 冷却中/未就绪的跳过：SKIPPED_CD / SKIPPED_NOT_READY
        - 条件不满足的网关：GW_COND_FALSE
        其它（SUCCESS / GW_END / GW_EXEC_* / GW_JUMP_* / GW_TAKEN / ...）都展示。
        """
        o = (ev.outcome or "").strip().upper()
        if o in ("SKIPPED_CD", "SKIPPED_NOT_READY", "GW_COND_FALSE"):
            return True
        return False

    # ---------- 填充表格 + 时间轴 ----------

    def _populate_table(self, events: List[SimEvent], result) -> None:
        self._table.setRowCount(len(events))

        for i, ev in enumerate(events):
            # 辅助：后 6 位
            mid = (ev.mode_id or "")
            tid = (ev.track_id or "")
            mid6 = mid[-6:] if mid else ""
            tid6 = tid[-6:] if tid else ""

            t_ms = int(ev.t_ms)
            t_s = t_ms / 1000.0

            def cell(v, center=True):
                item = QTableWidgetItem(str(v))
                if center:
                    item.setTextAlignment(Qt.AlignCenter)
                return item

            self._table.setItem(i, 0, cell(ev.index))
            self._table.setItem(i, 1, cell(t_ms))
            self._table.setItem(i, 2, cell(f"{t_s:.3f}"))
            self._table.setItem(i, 3, cell(ev.scope))
            self._table.setItem(i, 4, cell(mid6))
            self._table.setItem(i, 5, cell(tid6))
            self._table.setItem(i, 6, QTableWidgetItem(ev.label or ""))
            self._table.setItem(i, 7, cell(ev.node_kind))
            self._table.setItem(i, 8, cell(ev.outcome))
            self._table.setItem(i, 9, QTableWidgetItem(ev.reason or ""))

        self._table.resizeColumnsToContents()

        # 时间轴视图
        self._timeline.set_events(events)
        self._update_zoom_label()

        # 汇总信息：
        # - 展示的事件数 = len(events)
        # - 总模拟时长 = result.final_time_ms
        total_visible = len(events)
        final_ms = int(result.final_time_ms or 0)
        final_s = final_ms / 1000.0

        self._lbl_summary.setText(
            f"推演完成：展示事件数={total_visible}（已过滤跳过/CD/条件不满足），"
            f"模拟总时长={final_ms} ms (~{final_s:.3f} s)，"
            f"Preset ID={result.preset_id or ''!r}"
        )

    # ---------- 时间轴缩放 ----------

    def _update_zoom_label(self) -> None:
        ratio = self._timeline.zoom_ratio()
        pct = int(ratio * 100 + 0.5)
        self._lbl_zoom.setText(f"{pct:d}%")

    def _on_zoom_in_clicked(self) -> None:
        self._timeline.zoom_in()
        self._update_zoom_label()

    def _on_zoom_out_clicked(self) -> None:
        self._timeline.zoom_out()
        self._update_zoom_label()

    def _on_zoom_reset_clicked(self) -> None:
        self._timeline.reset_zoom()
        self._update_zoom_label()

    # ---------- 事件详情 ----------

    def _show_event_detail(self, row: int) -> None:
        if row < 0 or row >= self._table.rowCount():
            return

        def txt(r, c):
            item = self._table.item(r, c)
            return item.text() if item is not None else ""

        idx = txt(row, 0)
        t_ms = txt(row, 1)
        t_s = txt(row, 2)
        scope = txt(row, 3)
        mode6 = txt(row, 4)
        track6 = txt(row, 5)
        label = txt(row, 6)
        kind = txt(row, 7)
        outcome = txt(row, 8)
        reason = txt(row, 9)

        lines = [
            f"事件序号(原 index): {idx}",
            f"时间: {t_ms} ms (~{t_s} s)",
            f"作用域(scope): {scope}",
            f"模式ID后6: {mode6}",
            f"轨道ID后6: {track6}",
            f"节点标签: {label}",
            f"节点类型: {kind}",
            f"结果(outcome): {outcome}",
        ]
        if reason:
            lines.append(f"原因(reason): {reason}")

        QMessageBox.information(
            self,
            "事件详情",
            "\n".join(lines),
            QMessageBox.Ok,
        )

    def _on_cell_double_clicked(self, row: int, col: int) -> None:  # noqa: ARG002
        if row < 0:
            return
        # row 是“可见列表”中的索引，直接高亮这行
        self._timeline.highlight_index(row)
        self._show_event_detail(row)

    def _on_timeline_event_clicked(self, index: int) -> None:
        """
        时间轴点击事件：联动表格选中 & 弹出详情。
        index 是“可见列表”中的索引。
        """
        row = int(index)
        if row < 0 or row >= self._table.rowCount():
            return
        self._table.selectRow(row)
        self._show_event_detail(row)