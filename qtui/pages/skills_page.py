# qtui/pages/skills_page.py
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QComboBox,
    QTextEdit,
    QTabWidget,
    QPushButton,
    QDoubleSpinBox,
)
from PySide6.QtCore import QTimer

from core.profiles import ProfileContext
from core.models.common import clamp_int
from core.models.skill import Skill
from core.pick.capture import ScreenCapture
from core.app.services.app_services import AppServices

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


class SkillsPage(RecordCrudPage):
    """
    技能配置页面（Qt 版）：
    - 左侧：技能列表（使用 RecordCrudPage 提供的通用 CRUD 底座）
    - 右侧：QTabWidget 三个标签页（基本 / 像素 / 备注）
    - 使用 AppServices.skills 进行数据读写
    - 脏状态通过 ProfileSession.dirty（skills 部分）更新“未保存*”
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
            raise RuntimeError("SkillsPage requires services (cannot be None)")

        self._ctx = ctx
        self._services = services
        self._notify = notify
        self._start_pick = start_pick
        self._cap = ScreenCapture()

        # 初始化通用 CRUD UI（左表 + 右侧容器）
        super().__init__(
            ctx=ctx,
            notify=notify,
            page_title="技能配置",
            record_noun="技能",
            columns=[
                ColumnDef("enabled", "启用", 52, "center"),
                ColumnDef("name", "名称", 140, "w"),
                ColumnDef("idshort", "ID", 80, "w"),
                ColumnDef("key", "触发键", 60, "center"),
                ColumnDef("pos", "坐标", 90, "center"),
                ColumnDef("hex", "颜色", 80, "center"),
                ColumnDef("tol", "容差", 60, "center"),
                ColumnDef("readbar", "读条(ms)", 80, "center"),
                ColumnDef("cd", "冷却(s)", 80, "center"),  # 新增：冷却时间
            ],
            parent=parent,
        )

        # 脏状态订阅（skills 部分）
        self.enable_uow_dirty_indicator(part_key="skills", session=services.session)

        # 右侧表单：Notebook（TabWidget）
        self._tabs = QTabWidget(self.right_body)
        rb_layout = self.right_body.layout()
        if rb_layout is None:
            rb_layout = QVBoxLayout(self.right_body)
        rb_layout.addWidget(self._tabs)

        tab_basic = QWidget(self._tabs)
        tab_pixel = QWidget(self._tabs)
        tab_note = QWidget(self._tabs)

        self._tabs.addTab(tab_basic, "基本")
        self._tabs.addTab(tab_pixel, "像素")
        self._tabs.addTab(tab_note, "备注")

        # Vars / widgets
        self._building_form = False
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.timeout.connect(lambda: self._apply_form_to_current(auto_save=False))

        self._build_tab_basic(tab_basic)
        self._build_tab_pixel(tab_pixel)
        self._build_tab_note(tab_note)
        self._install_dirty_watchers()

        # 初始刷新列表
        self.refresh_tree()

    # ---------- 生命周期辅助 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        """
        Profile 切换时调用，刷新内部 ctx 和列表。
        """
        self._ctx = ctx
        try:
            self._apply_timer.stop()
        except Exception:
            log.exception("SkillsPage.set_context: failed to stop apply_timer")
        self._current_id = None
        self.refresh_tree()

    # ---------- RecordCrudPage 抽象实现 ----------

    def _records(self) -> list:
        return self._ctx.skills.skills

    def _save_to_disk(self) -> bool:
        try:
            self._services.skills.save_cmd(backup=self._ctx.base.io.backup_on_save)
            self._services.notify_dirty()
            return True
        except Exception as e:
            self._notify.error("保存 skills.json 失败", detail=str(e))
            return False

    def _reload_from_disk(self) -> None:
        self._services.skills.reload_cmd()

    def _make_new_record(self) -> Skill:
        return self._services.skills.create_cmd(name="新技能")

    def _clone_record(self, record: Skill) -> Skill:
        clone = self._services.skills.clone_cmd(record.id)
        if clone is None:
            raise RuntimeError("clone_cmd returned None")
        return clone

    def _delete_record_by_id(self, rid: str) -> None:
        self._services.skills.delete_cmd(rid)

    def _record_id(self, record: Skill) -> str:
        return record.id

    def _record_title(self, record: Skill) -> str:
        return record.name

    def _record_row_values(self, s: Skill) -> tuple:
        sid = s.id or ""
        short = sid[-6:] if len(sid) >= 6 else sid

        try:
            rx, ry = self._cap.abs_to_rel(int(s.pixel.vx), int(s.pixel.vy), s.pixel.monitor or "primary")
        except Exception:
            rx, ry = int(s.pixel.vx), int(s.pixel.vy)

        pos = f"({rx},{ry})"
        hx = rgb_to_hex(s.pixel.color.r, s.pixel.color.g, s.pixel.color.b)

        cooldown_s = f"{s.cooldown_ms / 1000.0:.2f}" if s.cooldown_ms else ""

        return (
            "是" if s.enabled else "否",
            s.name,
            short,
            s.trigger.key,
            pos,
            hx,
            str(s.pixel.tolerance),
            str(s.cast.readbar_ms),
            cooldown_s,
        )

    # ---------- 表单 UI ----------

    def _build_tab_basic(self, parent: QWidget) -> None:
        layout = QFormLayout(parent)

        self.txt_id = QLineEdit(parent)
        self.txt_id.setReadOnly(True)
        layout.addRow("ID", self.txt_id)

        self.txt_name = QLineEdit(parent)
        layout.addRow("名称", self.txt_name)

        self.chk_enabled = QCheckBox("启用", parent)
        layout.addRow("", self.chk_enabled)

        self.txt_trigger_key = QLineEdit(parent)
        layout.addRow("触发键", self.txt_trigger_key)

        self.spin_readbar = QSpinBox(parent)
        self.spin_readbar.setRange(0, 10**9)
        self.spin_readbar.setSingleStep(10)
        layout.addRow("读条时间(ms)", self.spin_readbar)

        # -------- 通用游戏元信息 --------
        layout.addRow(QLabel("--- 游戏元数据 (可选) ---", parent), QLabel("", parent))

        self.spin_game_id = QSpinBox(parent)
        self.spin_game_id.setRange(0, 2**31 - 1)
        self.spin_game_id.setSingleStep(1)
        layout.addRow("游戏技能ID(game_id)", self.spin_game_id)

        self.spin_cooldown_s = QDoubleSpinBox(parent)
        self.spin_cooldown_s.setRange(0.0, 600.0)
        self.spin_cooldown_s.setSingleStep(0.25)
        self.spin_cooldown_s.setDecimals(2)
        layout.addRow("冷却时间(s)", self.spin_cooldown_s)

        self.spin_radius = QSpinBox(parent)
        self.spin_radius.setRange(0, 100000)
        self.spin_radius.setSingleStep(10)
        layout.addRow("技能半径", self.spin_radius)

        self.txt_icon_url = QLineEdit(parent)
        self.txt_icon_url.setPlaceholderText("技能图标 URL，可选")
        layout.addRow("图标 URL", self.txt_icon_url)

        self.txt_game_desc = QTextEdit(parent)
        self.txt_game_desc.setPlaceholderText("官方技能描述（可选，仅用于展示）")
        self.txt_game_desc.setFixedHeight(60)
        layout.addRow("游戏描述", self.txt_game_desc)

    def _build_tab_pixel(self, parent: QWidget) -> None:
        vbox = QVBoxLayout(parent)

        # 第一组：屏幕 + 坐标
        form_head = QFormLayout()
        vbox.addLayout(form_head)

        self.cmb_monitor = QComboBox(parent)
        self.cmb_monitor.addItems(["primary", "all", "monitor_1", "monitor_2"])
        form_head.addRow("屏幕", self.cmb_monitor)

        self.spin_x = QSpinBox(parent)
        self.spin_x.setRange(0, 9999999)
        self.spin_x.setSingleStep(1)
        form_head.addRow("X(rel)", self.spin_x)

        self.spin_y = QSpinBox(parent)
        self.spin_y.setRange(0, 9999999)
        self.spin_y.setSingleStep(1)
        form_head.addRow("Y(rel)", self.spin_y)

        # 颜色预览
        self._swatch = ColorSwatch(parent)
        vbox.addWidget(self._swatch)

        # 第二组：RGB
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

        # 第三组：容差 + 采样模式/半径
        form_more = QFormLayout()
        vbox.addLayout(form_more)

        self.spin_tol = QSpinBox(parent)
        self.spin_tol.setRange(0, 255)
        form_more.addRow("容差", self.spin_tol)

        self.cmb_sample_mode = QComboBox(parent)
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
        btn_test = QPushButton("测试当前像素是否匹配", parent)
        btn_test.clicked.connect(self.test_current_pixel)
        vbox.addWidget(btn_test)

        vbox.addStretch(1)

    def _build_tab_note(self, parent: QWidget) -> None:
        vbox = QVBoxLayout(parent)
        self.txt_note = QTextEdit(parent)
        self.txt_note.setPlaceholderText("备注...")
        vbox.addWidget(self.txt_note)

    # ---------- 表单数据加载/应用 ----------

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
            self.chk_enabled.setChecked(True)
            self.txt_trigger_key.setText("")
            self.spin_readbar.setValue(0)

            # 新增字段
            self.spin_game_id.setValue(0)
            self.spin_cooldown_s.setValue(0.0)
            self.spin_radius.setValue(0)
            self.txt_icon_url.setText("")
            self.txt_game_desc.setPlainText("")

            # 像素相关
            self.cmb_monitor.setCurrentText("primary")
            self.spin_x.setValue(0)
            self.spin_y.setValue(0)
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

        s = self._find_skill(rid)
        if s is None:
            return

        self._current_id = rid
        short = rid[-6:] if len(rid) >= 6 else rid
        self.set_header_title(f"{s.name}  [{short}]")

        self._building_form = True
        try:
            # 基本
            self.txt_id.setText(s.id)
            self.txt_name.setText(s.name)
            self.chk_enabled.setChecked(bool(s.enabled))
            self.txt_trigger_key.setText(s.trigger.key)
            self.spin_readbar.setValue(int(s.cast.readbar_ms))

            # 游戏元信息
            self.spin_game_id.setValue(int(s.game_id or 0))
            self.spin_cooldown_s.setValue((s.cooldown_ms or 0) / 1000.0)
            self.spin_radius.setValue(int(s.radius or 0))
            self.txt_icon_url.setText(s.icon_url or "")
            self.txt_game_desc.setPlainText(s.game_desc or "")

            # 像素
            self.cmb_monitor.setCurrentText(s.pixel.monitor or "primary")
            try:
                rx, ry = self._cap.abs_to_rel(
                    int(s.pixel.vx),
                    int(s.pixel.vy),
                    self.cmb_monitor.currentText(),
                )
            except Exception:
                rx, ry = 0, 0
            self.spin_x.setValue(int(rx))
            self.spin_y.setValue(int(ry))

            self.spin_r.setValue(int(s.pixel.color.r))
            self.spin_g.setValue(int(s.pixel.color.g))
            self.spin_b.setValue(int(s.pixel.color.b))
            self._swatch.set_rgb(self.spin_r.value(), self.spin_g.value(), self.spin_b.value())

            self.spin_tol.setValue(int(s.pixel.tolerance))
            disp_mode = SAMPLE_VALUE_TO_DISPLAY.get(s.pixel.sample.mode or "single", "单像素")
            self.cmb_sample_mode.setCurrentText(disp_mode)
            self.spin_sample_radius.setValue(int(s.pixel.sample.radius))

            # 备注
            self.txt_note.setPlainText(s.note or "")
        finally:
            self._building_form = False

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        if self._building_form or not self._current_id:
            return True

        self._cancel_pending_apply()

        sid = self._current_id

        mon = (self.cmb_monitor.currentText() or "primary").strip() or "primary"
        rel_x = clamp_int(int(self.spin_x.value()), 0, 10**9)
        rel_y = clamp_int(int(self.spin_y.value()), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        from core.app.services.skills_service import SkillFormPatch

        patch = SkillFormPatch(
            name=self.txt_name.text(),
            enabled=bool(self.chk_enabled.isChecked()),
            trigger_key=self.txt_trigger_key.text(),
            readbar_ms=int(self.spin_readbar.value()),
            monitor=mon,
            vx=int(vx),
            vy=int(vy),
            r=int(self.spin_r.value()),
            g=int(self.spin_g.value()),
            b=int(self.spin_b.value()),
            tolerance=int(self.spin_tol.value()),
            sample_mode=SAMPLE_DISPLAY_TO_VALUE.get(self.cmb_sample_mode.currentText(), "single"),
            sample_radius=int(self.spin_sample_radius.value()),
            note=self.txt_note.toPlainText().rstrip("\n"),

            game_id=int(self.spin_game_id.value()),
            game_desc=self.txt_game_desc.toPlainText(),
            icon_url=self.txt_icon_url.text(),
            cooldown_ms=int(self.spin_cooldown_s.value() * 1000),
            radius=int(self.spin_radius.value()),
        )

        try:
            changed, _saved = self._services.skills.apply_form_patch(sid, patch, auto_save=auto_save)
            if changed:
                self.update_tree_row(sid)
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
                log.debug("SkillsPage._install_dirty_watchers: failed to update swatch", exc_info=True)
            self._apply_timer.start(200)

        # basic
        self.txt_name.textChanged.connect(on_any_changed)
        self.chk_enabled.toggled.connect(on_any_changed)
        self.txt_trigger_key.textChanged.connect(on_any_changed)
        self.spin_readbar.valueChanged.connect(on_any_changed)

        # 游戏元信息
        self.spin_game_id.valueChanged.connect(on_any_changed)
        self.spin_cooldown_s.valueChanged.connect(on_any_changed)
        self.spin_radius.valueChanged.connect(on_any_changed)
        self.txt_icon_url.textChanged.connect(on_any_changed)
        self.txt_game_desc.textChanged.connect(on_any_changed)

        # pixel
        self.cmb_monitor.currentTextChanged.connect(on_any_changed)
        self.spin_x.valueChanged.connect(on_any_changed)
        self.spin_y.valueChanged.connect(on_any_changed)
        self.spin_r.valueChanged.connect(on_any_changed)
        self.spin_g.valueChanged.connect(on_any_changed)
        self.spin_b.valueChanged.connect(on_any_changed)
        self.spin_tol.valueChanged.connect(on_any_changed)
        self.cmb_sample_mode.currentTextChanged.connect(on_any_changed)
        self.spin_sample_radius.valueChanged.connect(on_any_changed)

        # note
        self.txt_note.textChanged.connect(on_any_changed)

    # ---------- 辅助 ----------

    def _find_skill(self, sid: str) -> Optional[Skill]:
        for s in self._ctx.skills.skills:
            if s.id == sid:
                return s
        return None

    def flush_to_model(self) -> None:
        """
        供 UnsavedGuard 使用：把表单状态写回模型（不自动保存）。
        """
        try:
            self._apply_form_to_current(auto_save=False)
        except Exception:
            log.exception("SkillsPage.flush_to_model: _apply_form_to_current failed")

    # ---------- 取色 / 测试 ----------

    def request_pick_current(self) -> None:
        """
        从当前技能发起取色：
        - 先 flush 表单到模型
        - 再根据技能像素配置构造采样参数
        - 调用 MainWindow 注入的 start_pick
        """
        if not self.current_id:
            self._notify.error("请先选择一个技能")
            return

        if not self._apply_form_to_current(auto_save=False):
            return

        sid = self.current_id
        s = self._find_skill(sid)
        if s is None:
            self._notify.error("当前技能不存在")
            return

        sample_mode = s.pixel.sample.mode or "single"
        sample_radius = int(getattr(s.pixel.sample, "radius", 0) or 0)
        monitor = s.pixel.monitor or "primary"

        def _on_confirm(c) -> None:
            applied, saved = self._services.skills.apply_pick_cmd(
                sid,
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
                self.update_tree_row(sid)
            except Exception:
                log.exception("SkillsPage.request_pick_current: update_tree_row failed")

            if self.current_id == sid:
                try:
                    self._load_into_form(sid)
                except Exception:
                    log.exception("SkillsPage.request_pick_current: _load_into_form failed")

            if getattr(c, "hex", ""):
                if saved:
                    self._notify.info(f"取色已应用并保存: {c.hex}")
                else:
                    self._notify.status_msg(f"取色已应用(未保存): {c.hex}", ttl_ms=2000)

        self._start_pick(
            record_type="skill_pixel",
            record_id=sid,
            sample_mode=sample_mode,
            sample_radius=sample_radius,
            monitor=monitor,
            on_confirm=_on_confirm,
        )

    def test_current_pixel(self) -> None:
        """
        基于当前技能像素配置，从屏幕采样一次颜色，并与配置的颜色+容差比较。
        """
        if not self.current_id:
            self._notify.error("请先选择一个技能")
            return

        if not self._apply_form_to_current(auto_save=False):
            return

        sid = self.current_id
        s = self._find_skill(sid)
        if s is None:
            self._notify.error("当前技能不存在")
            return

        from core.pick.capture import SampleSpec

        sample = SampleSpec(
            mode=s.pixel.sample.mode or "single",
            radius=int(getattr(s.pixel.sample, "radius", 0) or 0),
        )
        mon = s.pixel.monitor or "primary"

        try:
            r, g, b = self._cap.get_rgb_scoped_abs(
                x_abs=int(s.pixel.vx),
                y_abs=int(s.pixel.vy),
                sample=sample,
                monitor_key=mon,
                require_inside=False,
            )
        except Exception as e:
            self._notify.error("测试取色失败", detail=str(e))
            return

        exp_r, exp_g, exp_b = int(s.pixel.color.r), int(s.pixel.color.g), int(s.pixel.color.b)
        tol = int(s.pixel.tolerance)

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