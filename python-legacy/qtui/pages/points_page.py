# qtui/pages/points_page.py
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QTextEdit,
    QTabWidget,
    QPushButton,
)
from PySide6.QtCore import QTimer

from core.profiles import ProfileContext
from core.models.common import clamp_int
from core.models.point import Point

from core.pick.capture import ScreenCapture
from core.app.services.app_services import AppServices
from core.io.json_store import now_iso_utc

from qtui.notify import UiNotify
from qtui.pages.record_crud_page import RecordCrudPage, ColumnDef
from qtui.widgets.color_swatch import ColorSwatch

import logging

log = logging.getLogger(__name__)

SAMPLE_DISPLAY_TO_VALUE = {"单像素": "single", "方形均值": "mean_square"}
SAMPLE_VALUE_TO_DISPLAY = {v: k for k, v in SAMPLE_DISPLAY_TO_VALUE.items()}


def rgb_to_hex(r: int, g: int, b: int) -> str:
    r = clamp_int(int(r), 0, 255)
    g = clamp_int(int(g), 0, 255)
    b = clamp_int(int(b), 0, 255)
    return f"#{r:02X}{g:02X}{b:02X}"


class PointsPage(RecordCrudPage):
    """
    取色点位配置页面（Qt 版）：
    - 左侧：点位列表（使用 RecordCrudPage 通用 CRUD UI）
    - 右侧：QTabWidget（三个标签页：基本 / 颜色&采样 / 备注）
    - 使用 AppServices.points 进行数据读写
    - 脏状态通过 ProfileSession.dirty（points 部分）更新“未保存*”
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        services: AppServices,
        notify: UiNotify,
        start_pick,
        parent: Optional[QWidget] = None,
    ) -> None:
        if services is None:
            raise RuntimeError("PointsPage requires services (cannot be None)")

        self._ctx = ctx
        self._services = services
        self._notify = notify
        self._start_pick = start_pick
        self._cap = ScreenCapture()

        super().__init__(
            ctx=ctx,
            notify=notify,
            page_title="取色点位配置",
            record_noun="点位",
            columns=[
                ColumnDef("name", "名称", 150, "w"),
                ColumnDef("idshort", "ID", 80, "w"),
                ColumnDef("monitor", "屏幕", 80, "center"),
                ColumnDef("pos", "坐标", 90, "center"),
                ColumnDef("hex", "颜色", 80, "center"),
                ColumnDef("tol", "容差", 60, "center"),
                ColumnDef("captured_at", "采集时间", 160, "w"),
            ],
            parent=parent,
        )

        # 脏状态订阅（points 部分）
        self.enable_uow_dirty_indicator(part_key="points", session=services.session)

        # 右侧表单：Notebook
        self._tabs = QTabWidget(self.right_body)
        rb_layout = self.right_body.layout()
        if rb_layout is None:
            rb_layout = QVBoxLayout(self.right_body)
        rb_layout.addWidget(self._tabs)

        tab_basic = QWidget(self._tabs)
        tab_color = QWidget(self._tabs)
        tab_note = QWidget(self._tabs)

        self._tabs.addTab(tab_basic, "基本")
        self._tabs.addTab(tab_color, "颜色&采样")
        self._tabs.addTab(tab_note, "备注")

        # 状态
        self._building_form = False
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.timeout.connect(lambda: self._apply_form_to_current(auto_save=False))

        self._build_tab_basic(tab_basic)
        self._build_tab_color(tab_color)
        self._build_tab_note(tab_note)
        self._install_dirty_watchers()

        self.refresh_tree()

    # ---------- 上下文切换 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        try:
            self._apply_timer.stop()
        except Exception:
            log.exception("PointsPage.set_context: failed to stop apply_timer")
        self._current_id = None
        self.refresh_tree()

    # ---------- RecordCrudPage 抽象实现 ----------

    def _records(self) -> list:
        return self._ctx.points.points

    def _save_to_disk(self) -> bool:
        try:
            self._services.points.save_cmd(backup=self._ctx.base.io.backup_on_save)
            self._services.notify_dirty()
            return True
        except Exception as e:
            self._notify.error("保存 points.json 失败", detail=str(e))
            return False

    def _reload_from_disk(self) -> None:
        self._services.points.reload_cmd()

    def _make_new_record(self) -> Point:
        return self._services.points.create_cmd(name="新点位")

    def _clone_record(self, record: Point) -> Point:
        clone = self._services.points.clone_cmd(record.id)
        if clone is None:
            raise RuntimeError("clone_cmd returned None")
        return clone

    def _delete_record_by_id(self, rid: str) -> None:
        self._services.points.delete_cmd(rid)

    def _record_id(self, record: Point) -> str:
        return record.id

    def _record_title(self, record: Point) -> str:
        return record.name

    def _record_row_values(self, p: Point) -> tuple:
        pid = p.id or ""
        short = pid[-6:] if len(pid) >= 6 else pid

        try:
            rx, ry = self._cap.abs_to_rel(int(p.vx), int(p.vy), p.monitor or "primary")
        except Exception:
            rx, ry = int(p.vx), int(p.vy)

        pos = f"({rx},{ry})"
        hx = rgb_to_hex(p.color.r, p.color.g, p.color.b)
        tol = str(int(getattr(p, "tolerance", 0) or 0))
        return (p.name, short, p.monitor, pos, hx, tol, p.captured_at)

    # ---------- 表单 UI ----------

    def _build_tab_basic(self, parent: QWidget) -> None:
        layout = QFormLayout(parent)

        self.txt_id = QLineEdit(parent)
        self.txt_id.setReadOnly(True)
        layout.addRow("ID", self.txt_id)

        self.txt_name = QLineEdit(parent)
        layout.addRow("名称", self.txt_name)

        self.cmb_monitor = QComboBox(parent)
        self.cmb_monitor.addItems(["primary", "all", "monitor_1", "monitor_2"])
        layout.addRow("屏幕", self.cmb_monitor)

        self.spin_x = QSpinBox(parent)
        self.spin_x.setRange(0, 9999999)
        self.spin_x.setSingleStep(1)
        layout.addRow("X(rel)", self.spin_x)

        self.spin_y = QSpinBox(parent)
        self.spin_y.setRange(0, 9999999)
        self.spin_y.setSingleStep(1)
        layout.addRow("Y(rel)", self.spin_y)

        row = QHBoxLayout()
        self.txt_captured_at = QLineEdit(parent)
        self.txt_captured_at.setReadOnly(True)
        btn_touch = QPushButton("更新时间(captured_at=now)", parent)
        btn_touch.clicked.connect(self._touch_time)
        row.addWidget(self.txt_captured_at)
        row.addWidget(btn_touch)
        layout.addRow("captured_at", row)

    def _build_tab_color(self, parent: QWidget) -> None:
        vbox = QVBoxLayout(parent)

        self._swatch = ColorSwatch(parent)
        vbox.addWidget(self._swatch)

        # RGB
        form_rgb = QFormLayout()
        vbox.addLayout(form_rgb)

        self.spin_r = QSpinBox(parent)
        self.spin_r.setRange(0, 255)
        form_rgb.addRow("R", self.spin_r)

        self.spin_g = QSpinBox(parent)
        self.spin_g.setRange(0, 255)
        form_rgb.addRow("G", self.spin_g)

        self.spin_b = QSpinBox(parent)
        self.spin_b.setRange(0, 255)
        form_rgb.addRow("B", self.spin_b)

        # 容差 + 采样
        form_more = QFormLayout()
        vbox.addLayout(form_more)

        self.spin_tol = QSpinBox(parent)
        self.spin_tol.setRange(0, 255)
        form_more.addRow("容差", self.spin_tol)

        self.cmb_sample_mode = QComboBox(parent)
        self.cmb_sample_mode.setEditable(False)
        self.cmb_sample_mode.addItems(list(SAMPLE_DISPLAY_TO_VALUE.keys()))
        form_more.addRow("采样模式", self.cmb_sample_mode)

        self.spin_sample_radius = QSpinBox(parent)
        self.spin_sample_radius.setRange(0, 50)
        form_more.addRow("半径", self.spin_sample_radius)

        # 取色按钮
        btn_pick = QPushButton("从屏幕取色（按确认热键确认）", parent)
        btn_pick.clicked.connect(self.request_pick_current)
        vbox.addWidget(btn_pick)

        # 新增：测试按钮
        btn_test = QPushButton("测试当前点位是否匹配", parent)
        btn_test.clicked.connect(self.test_current_point)
        vbox.addWidget(btn_test)

        vbox.addStretch(1)

    def _build_tab_note(self, parent: QWidget) -> None:
        vbox = QVBoxLayout(parent)
        self.txt_note = QTextEdit(parent)
        self.txt_note.setPlaceholderText("备注...")
        vbox.addWidget(self.txt_note)

    # ---------- 表单加载/应用 ----------

    def _cancel_pending_apply(self) -> None:
        try:
            self._apply_timer.stop()
        except Exception:
            pass

    def _clear_form(self) -> None:
        self._cancel_pending_apply()
        self.set_header_title("未选择")
        self._building_form = True
        try:
            self._current_id = None
            self.txt_id.setText("")
            self.txt_name.setText("")
            self.cmb_monitor.setCurrentText("primary")
            self.spin_x.setValue(0)
            self.spin_y.setValue(0)
            self.txt_captured_at.setText("")
            self.spin_r.setValue(0)
            self.spin_g.setValue(0)
            self.spin_b.setValue(0)
            self._swatch.set_rgb(0, 0, 0)
            self.spin_tol.setValue(0)
            self.cmb_sample_mode.setCurrentText("单像素")
            self.spin_sample_radius.setValue(0)
            self.txt_note.setPlainText("")
        finally:
            self._building_form = False

    def _load_into_form(self, rid: str) -> None:
        self._cancel_pending_apply()

        p = self._find_point(rid)
        if p is None:
            return
        self._current_id = rid
        short = rid[-6:] if len(rid) >= 6 else rid
        self.set_header_title(f"{p.name}  [{short}]")

        self._building_form = True
        try:
            self.txt_id.setText(p.id)
            self.txt_name.setText(p.name)
            self.cmb_monitor.setCurrentText(p.monitor or "primary")

            try:
                rx, ry = self._cap.abs_to_rel(int(p.vx), int(p.vy), self.cmb_monitor.currentText())
            except Exception:
                rx, ry = 0, 0
            self.spin_x.setValue(int(rx))
            self.spin_y.setValue(int(ry))

            self.spin_r.setValue(int(p.color.r))
            self.spin_g.setValue(int(p.color.g))
            self.spin_b.setValue(int(p.color.b))
            self._swatch.set_rgb(self.spin_r.value(), self.spin_g.value(), self.spin_b.value())

            self.spin_tol.setValue(int(getattr(p, "tolerance", 0) or 0))

            self.txt_captured_at.setText(p.captured_at or "")
            self.cmb_sample_mode.setCurrentText(
                SAMPLE_VALUE_TO_DISPLAY.get(p.sample.mode or "single", "单像素")
            )
            self.spin_sample_radius.setValue(int(p.sample.radius))

            self.txt_note.setPlainText(p.note or "")
        finally:
            self._building_form = False

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        if self._building_form or not self._current_id:
            return True

        self._cancel_pending_apply()

        pid = self._current_id

        mon = (self.cmb_monitor.currentText() or "primary").strip() or "primary"
        rel_x = clamp_int(int(self.spin_x.value()), 0, 10**9)
        rel_y = clamp_int(int(self.spin_y.value()), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        from core.app.services.points_service import PointFormPatch

        patch = PointFormPatch(
            name=self.txt_name.text(),
            monitor=mon,
            vx=int(vx),
            vy=int(vy),
            r=int(self.spin_r.value()),
            g=int(self.spin_g.value()),
            b=int(self.spin_b.value()),
            tolerance=int(self.spin_tol.value()),
            captured_at=self.txt_captured_at.text(),
            sample_mode=SAMPLE_DISPLAY_TO_VALUE.get(self.cmb_sample_mode.currentText(), "single"),
            sample_radius=int(self.spin_sample_radius.value()),
            note=self.txt_note.toPlainText().rstrip("\n"),
        )

        try:
            changed, _saved = self._services.points.apply_form_patch(pid, patch, auto_save=auto_save)
            if changed:
                self.update_tree_row(pid)
        except Exception as e:
            self._notify.error("应用表单失败", detail=str(e))
            return False

        return True

    # ---------- 表单变更监听 ----------

    def _install_dirty_watchers(self) -> None:
        def on_any_changed(*_args) -> None:
            if self._building_form:
                return
            try:
                self._swatch.set_rgb(self.spin_r.value(), self.spin_g.value(), self.spin_b.value())
            except Exception:
                log.debug("PointsPage._install_dirty_watchers: failed to update swatch", exc_info=True)
            self._apply_timer.start(200)

        # basic
        self.txt_name.textChanged.connect(on_any_changed)
        self.cmb_monitor.currentTextChanged.connect(on_any_changed)
        self.spin_x.valueChanged.connect(on_any_changed)
        self.spin_y.valueChanged.connect(on_any_changed)
        self.txt_captured_at.textChanged.connect(on_any_changed)

        # color & sample
        self.spin_r.valueChanged.connect(on_any_changed)
        self.spin_g.valueChanged.connect(on_any_changed)
        self.spin_b.valueChanged.connect(on_any_changed)
        self.spin_tol.valueChanged.connect(on_any_changed)
        self.cmb_sample_mode.currentTextChanged.connect(on_any_changed)
        self.spin_sample_radius.valueChanged.connect(on_any_changed)

        # note
        self.txt_note.textChanged.connect(on_any_changed)

    # ---------- 辅助 ----------

    def _find_point(self, pid: str) -> Optional[Point]:
        for p in self._ctx.points.points:
            if p.id == pid:
                return p
        return None

    def _touch_time(self) -> None:
        self.txt_captured_at.setText(now_iso_utc())
        self._apply_timer.start(200)

    def flush_to_model(self) -> None:
        try:
            self._apply_form_to_current(auto_save=False)
        except Exception:
            log.exception("PointsPage.flush_to_model: _apply_form_to_current failed")

    # ---------- 取色 / 测试 ----------

    def request_pick_current(self) -> None:
        """
        从当前点位发起取色：
        - 先 flush 表单到模型
        - 再根据点位配置构造采样参数
        - 调用 MainWindow 注入的 start_pick
        """
        if not self.current_id:
            self._notify.error("请先选择一个点位")
            return

        if not self._apply_form_to_current(auto_save=False):
            return

        pid = self.current_id
        p = self._find_point(pid)
        if p is None:
            self._notify.error("当前点位不存在")
            return

        sample_mode = p.sample.mode or "single"
        sample_radius = int(getattr(p.sample, "radius", 0) or 0)
        monitor = p.monitor or "primary"

        def _on_confirm(c) -> None:
            applied, saved = self._services.points.apply_pick_cmd(
                pid,
                vx=c.vx,
                vy=c.vy,
                monitor=c.monitor,
                r=c.r,
                g=c.g,
                b=c.b,
            )
            if not applied:
                return

            try:
                self.update_tree_row(pid)
            except Exception:
                log.exception("PointsPage.request_pick_current: update_tree_row failed")

            if self.current_id == pid:
                try:
                    self._load_into_form(pid)
                except Exception:
                    log.exception("PointsPage.request_pick_current: _load_into_form failed")

            if getattr(c, "hex", ""):
                if saved:
                    self._notify.info(f"取色已应用并保存: {c.hex}")
                else:
                    self._notify.status_msg(f"取色已应用(未保存): {c.hex}", ttl_ms=2000)

        self._start_pick(
            record_type="point",
            record_id=pid,
            sample_mode=sample_mode,
            sample_radius=sample_radius,
            monitor=monitor,
            on_confirm=_on_confirm,
        )

    def test_current_point(self) -> None:
        """
        基于当前点位配置，从屏幕采样一次颜色，并与配置的颜色+容差比较。
        """
        if not self.current_id:
            self._notify.error("请先选择一个点位")
            return

        if not self._apply_form_to_current(auto_save=False):
            return

        pid = self.current_id
        p = self._find_point(pid)
        if p is None:
            self._notify.error("当前点位不存在")
            return

        from core.pick.capture import SampleSpec

        sample = SampleSpec(
            mode=p.sample.mode or "single",
            radius=int(getattr(p.sample, "radius", 0) or 0),
        )
        mon = p.monitor or "primary"

        try:
            r, g, b = self._cap.get_rgb_scoped_abs(
                x_abs=int(p.vx),
                y_abs=int(p.vy),
                sample=sample,
                monitor_key=mon,
                require_inside=False,
            )
        except Exception as e:
            self._notify.error("测试取色失败", detail=str(e))
            return

        exp_r, exp_g, exp_b = int(p.color.r), int(p.color.g), int(p.color.b)
        tol = int(getattr(p, "tolerance", 0) or 0)

        diff_r = abs(r - exp_r)
        diff_g = abs(g - exp_g)
        diff_b = abs(b - exp_b)
        max_diff = max(diff_r, diff_g, diff_b)

        measured_hex = rgb_to_hex(r, g, b)
        expected_hex = rgb_to_hex(exp_r, exp_g, exp_b)

        try:
            self._swatch.set_rgb(r, g, b)
        except Exception:
            pass

        if max_diff <= tol:
            self._notify.info(
                f"取色测试通过：当前 {measured_hex}，期望 {expected_hex}，最大通道差 {max_diff} ≤ 容差 {tol}"
            )
        else:
            self._notify.error(
                "取色测试未通过",
                detail=(
                    f"当前 {measured_hex}，期望 {expected_hex}，"
                    f"最大通道差 {max_diff} > 容差 {tol}"
                ),
            )