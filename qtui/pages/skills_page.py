from __future__ import annotations

from typing import Optional, Any, Dict, List

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
    QScrollArea,
    QGroupBox,
)
from PySide6.QtCore import QTimer, Qt

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
                ColumnDef("cd", "冷却(s)", 80, "center"),  # 冷却时间
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

            # 技能次数
            self.spin_shots_per_cycle.setValue(int(getattr(s, "shots_per_cycle", 1) or 1))

            # 游戏元信息
            self.spin_game_id.setValue(int(s.game_id or 0))
            self.spin_cooldown_s.setValue((s.cooldown_ms or 0) / 1000.0)
            self.spin_radius.setValue(int(s.radius or 0))
            self.txt_icon_url.setText(s.icon_url or "")
            self.txt_game_desc.setPlainText(s.game_desc or "")

            # 像素（主像素）
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

            # 弹药阶段像素列表 (ammo_stages)
            stages_data: list[dict[str, Any]] = []
            for st in getattr(s, "ammo_stages", []) or []:
                try:
                    charges = int(getattr(st, "charges_left", 0) or 0)
                    pix = st.pixel
                    mon2 = getattr(pix, "monitor", "primary") or "primary"
                    vx2 = int(getattr(pix, "vx", 0) or 0)
                    vy2 = int(getattr(pix, "vy", 0) or 0)
                    cr = int(getattr(pix.color, "r", 0) or 0)
                    cg = int(getattr(pix.color, "g", 0) or 0)
                    cb = int(getattr(pix.color, "b", 0) or 0)
                    tol2 = int(getattr(pix, "tolerance", 0) or 0)
                    smode = getattr(pix.sample, "mode", "single") or "single"
                    srad = int(getattr(pix.sample, "radius", 0) or 0)
                except Exception:
                    continue
                if charges <= 0:
                    continue
                stages_data.append(
                    {
                        "charges_left": charges,
                        "monitor": mon2,
                        "vx": vx2,
                        "vy": vy2,
                        "r": cr,
                        "g": cg,
                        "b": cb,
                        "tolerance": tol2,
                        "sample_mode": smode,
                        "sample_radius": srad,
                    }
                )

            if stages_data:
                count = len(stages_data)
                self._rebuild_ammo_stage_rows(count, stages_data=stages_data)
            else:
                count = int(getattr(s, "shots_per_cycle", 1) or 1)
                if count > 1:
                    self._rebuild_ammo_stage_rows(count, stages_data=None)
                else:
                    self._rebuild_ammo_stage_rows(0, stages_data=None)

            # 备注
            self.txt_note.setPlainText(s.note or "")
        finally:
            self._building_form = False

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        if self._building_form or not self._current_id:
            return True

        self._cancel_pending_apply()

        sid = self._current_id

        # 主像素：相对坐标 -> 绝对坐标
        mon = (self.cmb_monitor.currentText() or "primary").strip() or "primary"
        rel_x = clamp_int(int(self.spin_x.value()), 0, 10**9)
        rel_y = clamp_int(int(self.spin_y.value()), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        # 弹药阶段像素：收集 UI 数据（注意：这里直接使用 X/Y 作为绝对坐标）
        ammo_stages_data: list[dict[str, Any]] = []
        for row in getattr(self, "_ammo_stage_rows", []) or []:
            sp_ch = row.get("charges")
            cmb_mon = row.get("monitor")
            sp_x = row.get("x")
            sp_y = row.get("y")
            sp_r = row.get("r")
            sp_g = row.get("g")
            sp_b = row.get("b")
            sp_tol = row.get("tol")
            cmb_smode = row.get("sample_mode")
            sp_srad = row.get("sample_radius")

            if not (sp_ch and cmb_mon and sp_x and sp_y and sp_r and sp_g and sp_b and sp_tol and cmb_smode and sp_srad):
                continue

            charges = int(sp_ch.value() or 0)
            if charges <= 0:
                continue

            mon2 = (cmb_mon.currentText() or "primary").strip() or "primary"
            vx2 = int(sp_x.value())
            vy2 = int(sp_y.value())
            smode_disp = cmb_smode.currentText()
            smode = SAMPLE_DISPLAY_TO_VALUE.get(smode_disp, "single")

            ammo_stages_data.append(
                {
                    "charges_left": charges,
                    "monitor": mon2,
                    "vx": vx2,
                    "vy": vy2,
                    "r": int(sp_r.value()),
                    "g": int(sp_g.value()),
                    "b": int(sp_b.value()),
                    "tolerance": int(sp_tol.value()),
                    "sample_mode": smode,
                    "sample_radius": int(sp_srad.value()),
                }
            )

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

            shots_per_cycle=int(self.spin_shots_per_cycle.value()),
            ammo_stages=ammo_stages_data,
        )

        try:
            changed, _saved = self._services.skills.apply_form_patch(sid, patch, auto_save=auto_save)
            if changed:
                self.update_tree_row(sid)
        except Exception as e:
            self._notify.error("应用表单失败", detail=str(e))
            return False

        return True

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
            self.spin_shots_per_cycle.setValue(1)
            self.spin_game_id.setValue(0)
            self.spin_cooldown_s.setValue(0.0)
            self.spin_radius.setValue(0)
            self.txt_icon_url.setText("")
            self.txt_game_desc.setPlainText("")

            # 像素相关（主像素）
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

            # 弹药阶段像素行
            self._rebuild_ammo_stage_rows(0, stages_data=None)

            # 备注
            self.txt_note.setPlainText("")
        finally:
            self._building_form = False

    # ---------- 表单 UI ----------

    def _build_tab_basic(self, parent: QWidget) -> None:
        layout = QFormLayout(parent)
        # 收紧整体行距，靠上对齐
        layout.setVerticalSpacing(6)
        layout.setFormAlignment(Qt.AlignTop)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

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

        # 技能次数（多发技能用）
        self.spin_shots_per_cycle = QSpinBox(parent)
        self.spin_shots_per_cycle.setRange(1, 1000)
        self.spin_shots_per_cycle.setSingleStep(1)
        layout.addRow("技能次数(shots_per_cycle)", self.spin_shots_per_cycle)

        # -------- 游戏元数据标题行 --------
        header = QLabel("--- 游戏元数据 (可选) ---", parent)
        header.setStyleSheet("color: #aaaaaa;")
        layout.addRow(header)

        # 游戏技能 ID
        self.spin_game_id = QSpinBox(parent)
        self.spin_game_id.setRange(0, 2**31 - 1)
        self.spin_game_id.setSingleStep(1)
        layout.addRow("游戏技能ID(game_id)", self.spin_game_id)

        # 冷却时间（秒）
        self.spin_cooldown_s = QDoubleSpinBox(parent)
        self.spin_cooldown_s.setRange(0.0, 600.0)
        self.spin_cooldown_s.setSingleStep(0.25)
        self.spin_cooldown_s.setDecimals(2)
        layout.addRow("冷却时间(s)", self.spin_cooldown_s)

        # 技能半径
        self.spin_radius = QSpinBox(parent)
        self.spin_radius.setRange(0, 100000)
        self.spin_radius.setSingleStep(10)
        layout.addRow("技能半径", self.spin_radius)

        # 图标 URL
        self.txt_icon_url = QLineEdit(parent)
        self.txt_icon_url.setPlaceholderText("技能图标 URL，可选")
        layout.addRow("图标 URL", self.txt_icon_url)

        # 游戏描述
        self.txt_game_desc = QTextEdit(parent)
        self.txt_game_desc.setPlaceholderText("官方技能描述（可选，仅用于展示）")
        self.txt_game_desc.setFixedHeight(60)
        layout.addRow("游戏描述", self.txt_game_desc)

    def _build_tab_pixel(self, parent: QWidget) -> None:
        root_vbox = QVBoxLayout(parent)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(8)

        # -------- 主像素分组 --------
        grp_main = QGroupBox("主像素 (技能是否就绪 / 可用检测)", parent)
        main_layout = QVBoxLayout(grp_main)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 屏幕
        form_main = QFormLayout()
        form_main.setContentsMargins(0, 0, 0, 0)
        form_main.setSpacing(4)
        main_layout.addLayout(form_main)

        self.cmb_monitor = QComboBox(grp_main)
        self.cmb_monitor.addItems(["primary", "all", "monitor_1", "monitor_2"])
        form_main.addRow("屏幕", self.cmb_monitor)

        # 位置 X/Y 一行
        pos_widget = QWidget(grp_main)
        pos_h = QHBoxLayout(pos_widget)
        pos_h.setContentsMargins(0, 0, 0, 0)
        pos_h.setSpacing(4)

        self.spin_x = QSpinBox(grp_main)
        self.spin_x.setRange(0, 9999999)
        self.spin_x.setSingleStep(1)

        self.spin_y = QSpinBox(grp_main)
        self.spin_y.setRange(0, 9999999)
        self.spin_y.setSingleStep(1)

        pos_h.addWidget(QLabel("X(rel)", pos_widget))
        pos_h.addWidget(self.spin_x)
        pos_h.addSpacing(8)
        pos_h.addWidget(QLabel("Y(rel)", pos_widget))
        pos_h.addWidget(self.spin_y)
        pos_h.addStretch(1)

        form_main.addRow("位置", pos_widget)

        # 颜色预览（主像素）
        self._swatch = ColorSwatch(grp_main)
        main_layout.addWidget(self._swatch)

        # RGB 一行
        rgb_widget = QWidget(grp_main)
        rgb_h = QHBoxLayout(rgb_widget)
        rgb_h.setContentsMargins(0, 0, 0, 0)
        rgb_h.setSpacing(4)

        self.spin_r = QSpinBox(grp_main)
        self.spin_r.setRange(0, 255)
        self.spin_g = QSpinBox(grp_main)
        self.spin_g.setRange(0, 255)
        self.spin_b = QSpinBox(grp_main)
        self.spin_b.setRange(0, 255)

        rgb_h.addWidget(QLabel("R", rgb_widget))
        rgb_h.addWidget(self.spin_r)
        rgb_h.addSpacing(4)
        rgb_h.addWidget(QLabel("G", rgb_widget))
        rgb_h.addWidget(self.spin_g)
        rgb_h.addSpacing(4)
        rgb_h.addWidget(QLabel("B", rgb_widget))
        rgb_h.addWidget(self.spin_b)
        rgb_h.addStretch(1)

        rgb_form = QFormLayout()
        rgb_form.setContentsMargins(0, 0, 0, 0)
        rgb_form.setSpacing(4)
        rgb_form.addRow("颜色RGB", rgb_widget)
        main_layout.addLayout(rgb_form)

        # 容差 + 采样
        form_more = QFormLayout()
        form_more.setContentsMargins(0, 0, 0, 0)
        form_more.setSpacing(4)
        main_layout.addLayout(form_more)

        self.spin_tol = QSpinBox(grp_main)
        self.spin_tol.setRange(0, 255)
        form_more.addRow("容差", self.spin_tol)

        sample_widget = QWidget(grp_main)
        sample_h = QHBoxLayout(sample_widget)
        sample_h.setContentsMargins(0, 0, 0, 0)
        sample_h.setSpacing(4)

        self.cmb_sample_mode = QComboBox(grp_main)
        self.cmb_sample_mode.addItems(list(SAMPLE_DISPLAY_TO_VALUE.keys()))
        self.spin_sample_radius = QSpinBox(grp_main)
        self.spin_sample_radius.setRange(0, 50)

        sample_h.addWidget(self.cmb_sample_mode)
        sample_h.addSpacing(4)
        sample_h.addWidget(QLabel("半径", sample_widget))
        sample_h.addWidget(self.spin_sample_radius)
        sample_h.addStretch(1)

        form_more.addRow("采样", sample_widget)

        # 主像素 取色 + 测试 按钮一行
        btn_row = QWidget(grp_main)
        btn_h = QHBoxLayout(btn_row)
        btn_h.setContentsMargins(0, 0, 0, 0)
        btn_h.setSpacing(8)

        btn_pick = QPushButton("从屏幕取色（按确认热键确认）", grp_main)
        btn_pick.clicked.connect(self.request_pick_current)
        btn_h.addWidget(btn_pick)

        btn_test = QPushButton("测试当前像素是否匹配", grp_main)
        btn_test.clicked.connect(self.test_current_pixel)
        btn_h.addWidget(btn_test)

        btn_h.addStretch(1)
        main_layout.addWidget(btn_row)

        root_vbox.addWidget(grp_main)

        # -------- 弹药阶段分组（多发技能） --------
        grp_ammo = QGroupBox("弹药阶段像素 (多发技能用，每阶段一个独立像素点)", parent)
        ammo_outer_layout = QVBoxLayout(grp_ammo)
        ammo_outer_layout.setContentsMargins(8, 8, 8, 8)
        ammo_outer_layout.setSpacing(6)

        lbl_hint = QLabel(
            "当技能有多发弹药时，可以为每个阶段配置一个像素点：\n"
            "例如 shots_per_cycle=3 时，可配置剩余 3/2/1 发时各自的像素点。",
            grp_ammo,
        )
        lbl_hint.setWordWrap(True)
        ammo_outer_layout.addWidget(lbl_hint)

        scroll = QScrollArea(grp_ammo)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_inner = QWidget(scroll)
        self._ammo_stages_layout = QVBoxLayout(scroll_inner)
        self._ammo_stages_layout.setContentsMargins(0, 0, 0, 0)
        self._ammo_stages_layout.setSpacing(8)

        scroll.setWidget(scroll_inner)
        ammo_outer_layout.addWidget(scroll)

        self._ammo_stage_rows: list[dict[str, Any]] = []
        self._rebuild_ammo_stage_rows(0, stages_data=None)

        root_vbox.addWidget(grp_ammo)
        root_vbox.addStretch(1)

    def _build_tab_note(self, parent: QWidget) -> None:
        vbox = QVBoxLayout(parent)
        self.txt_note = QTextEdit(parent)
        self.txt_note.setPlaceholderText("备注...")
        vbox.addWidget(self.txt_note)

    # ---------- 表单数据加载/应用 辅助 ----------

    def _cancel_pending_apply(self) -> None:
        try:
            self._apply_timer.stop()
        except Exception:
            pass

    # ---------- 脏状态监听 ----------

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
        self.spin_shots_per_cycle.valueChanged.connect(self._on_shots_per_cycle_changed)

        # 游戏元信息
        self.spin_game_id.valueChanged.connect(on_any_changed)
        self.spin_cooldown_s.valueChanged.connect(on_any_changed)
        self.spin_radius.valueChanged.connect(on_any_changed)
        self.txt_icon_url.textChanged.connect(on_any_changed)
        self.txt_game_desc.textChanged.connect(on_any_changed)

        # pixel（主像素）
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

    def _on_shots_per_cycle_changed(self) -> None:
        """
        当技能次数(shots_per_cycle)变更时，重建弹药阶段像素行。
        简单策略：完全按新的 shots_per_cycle 重建行，原有阶段配置会丢失。
        """
        if self._building_form:
            return
        n = int(self.spin_shots_per_cycle.value() or 1)
        if n <= 1:
            self._rebuild_ammo_stage_rows(0, stages_data=None)
        else:
            self._rebuild_ammo_stage_rows(n, stages_data=None)
        # 标记脏
        self._apply_timer.start(200)

    def _rebuild_ammo_stage_rows(self, count: int, stages_data: Optional[list[dict[str, Any]]] = None) -> None:
        """
        重建弹药阶段像素行（多行布局 + 滚动区域）：
        - count: 行数
        - stages_data: 可选初始数据，每项包含
            {
                "charges_left": int,
                "monitor": str,
                "vx": int, "vy": int,
                "r": int, "g": int, "b": int,
                "tolerance": int,
                "sample_mode": str,
                "sample_radius": int,
            }
        UI 上每个阶段是一个小卡片：
            行1: 剩余弹药数
            行2: 屏幕 + X/Y（位置一行）
            行3: RGB（颜色一行）
            行4: 容差
            行5: 采样模式 + 半径
            行6: 取色 + 测试 按钮一行
        """
        # 清空旧行
        if hasattr(self, "_ammo_stage_rows") and self._ammo_stage_rows:
            for _ in self._ammo_stage_rows:
                pass

        if hasattr(self, "_ammo_stages_layout") and self._ammo_stages_layout is not None:
            while self._ammo_stages_layout.count() > 0:
                item = self._ammo_stages_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        self._ammo_stage_rows = []

        if count <= 0:
            return

        # 准备数据
        data_list: list[dict[str, Any]] = []
        if stages_data:
            data_list = list(stages_data)
        if not data_list:
            for ch in range(count, 0, -1):
                data_list.append(
                    {
                        "charges_left": ch,
                        "monitor": "primary",
                        "vx": 0,
                        "vy": 0,
                        "r": 0,
                        "g": 0,
                        "b": 0,
                        "tolerance": 0,
                        "sample_mode": "single",
                        "sample_radius": 0,
                    }
                )
        else:
            if len(data_list) > count:
                data_list = data_list[:count]
            elif len(data_list) < count:
                last_ch = data_list[-1].get("charges_left", 1) if data_list else 1
                for _ in range(count - len(data_list)):
                    last_ch = max(1, last_ch - 1)
                    data_list.append(
                        {
                            "charges_left": last_ch,
                            "monitor": "primary",
                            "vx": 0,
                            "vy": 0,
                            "r": 0,
                            "g": 0,
                            "b": 0,
                            "tolerance": 0,
                            "sample_mode": "single",
                            "sample_radius": 0,
                        }
                    )

        # 创建阶段卡片
        for i in range(count):
            row_data = data_list[i]
            ch = int(row_data.get("charges_left", 0) or 0)
            mon2 = (row_data.get("monitor", "primary") or "primary").strip() or "primary"
            vx2 = int(row_data.get("vx", 0) or 0)
            vy2 = int(row_data.get("vy", 0) or 0)
            rr = int(row_data.get("r", 0) or 0)
            gg = int(row_data.get("g", 0) or 0)
            bb = int(row_data.get("b", 0) or 0)
            tol2 = int(row_data.get("tolerance", 0) or 0)
            smode = row_data.get("sample_mode", "single") or "single"
            srad = int(row_data.get("sample_radius", 0) or 0)

            block = QGroupBox(self.right_body)
            block.setTitle(f"阶段 {i+1}")
            v = QVBoxLayout(block)
            v.setContentsMargins(6, 4, 6, 4)
            v.setSpacing(4)

            # 行1：剩余弹药数
            form_top = QFormLayout()
            form_top.setContentsMargins(0, 0, 0, 0)
            form_top.setSpacing(4)
            sp_charges = QSpinBox(block)
            sp_charges.setRange(0, 1000)
            sp_charges.setValue(ch)
            form_top.addRow("剩余弹药数", sp_charges)
            v.addLayout(form_top)

            # 行2：屏幕 + 位置(X/Y 一行)
            form_pos = QFormLayout()
            form_pos.setContentsMargins(0, 0, 0, 0)
            form_pos.setSpacing(4)

            cmb_mon = QComboBox(block)
            cmb_mon.addItems(["primary", "all", "monitor_1", "monitor_2"])
            cmb_mon.setCurrentText(mon2)
            form_pos.addRow("屏幕", cmb_mon)

            pos_widget = QWidget(block)
            pos_h = QHBoxLayout(pos_widget)
            pos_h.setContentsMargins(0, 0, 0, 0)
            pos_h.setSpacing(4)

            sp_x = QSpinBox(block)
            sp_x.setRange(0, 9999999)
            sp_x.setSingleStep(1)
            sp_x.setValue(vx2)

            sp_y = QSpinBox(block)
            sp_y.setRange(0, 9999999)
            sp_y.setSingleStep(1)
            sp_y.setValue(vy2)

            pos_h.addWidget(QLabel("X(像素)", pos_widget))
            pos_h.addWidget(sp_x)
            pos_h.addSpacing(8)
            pos_h.addWidget(QLabel("Y(像素)", pos_widget))
            pos_h.addWidget(sp_y)
            pos_h.addStretch(1)

            form_pos.addRow("位置", pos_widget)
            v.addLayout(form_pos)

            # 行3：RGB 一行
            form_rgb = QFormLayout()
            form_rgb.setContentsMargins(0, 0, 0, 0)
            form_rgb.setSpacing(4)

            rgb_widget = QWidget(block)
            rgb_h = QHBoxLayout(rgb_widget)
            rgb_h.setContentsMargins(0, 0, 0, 0)
            rgb_h.setSpacing(4)

            sp_r = QSpinBox(block)
            sp_r.setRange(0, 255)
            sp_r.setValue(rr)

            sp_g = QSpinBox(block)
            sp_g.setRange(0, 255)
            sp_g.setValue(gg)

            sp_b = QSpinBox(block)
            sp_b.setRange(0, 255)
            sp_b.setValue(bb)

            rgb_h.addWidget(QLabel("R", rgb_widget))
            rgb_h.addWidget(sp_r)
            rgb_h.addSpacing(4)
            rgb_h.addWidget(QLabel("G", rgb_widget))
            rgb_h.addWidget(sp_g)
            rgb_h.addSpacing(4)
            rgb_h.addWidget(QLabel("B", rgb_widget))
            rgb_h.addWidget(sp_b)
            rgb_h.addStretch(1)

            form_rgb.addRow("颜色RGB", rgb_widget)
            v.addLayout(form_rgb)

            # 行4：容差
            form_tol = QFormLayout()
            form_tol.setContentsMargins(0, 0, 0, 0)
            form_tol.setSpacing(4)
            sp_tol = QSpinBox(block)
            sp_tol.setRange(0, 255)
            sp_tol.setValue(tol2)
            form_tol.addRow("容差", sp_tol)
            v.addLayout(form_tol)

            # 行5：采样模式 + 半径
            form_sample = QFormLayout()
            form_sample.setContentsMargins(0, 0, 0, 0)
            form_sample.setSpacing(4)

            sample_widget = QWidget(block)
            sample_h = QHBoxLayout(sample_widget)
            sample_h.setContentsMargins(0, 0, 0, 0)
            sample_h.setSpacing(4)

            cmb_smode = QComboBox(block)
            cmb_smode.addItems(list(SAMPLE_DISPLAY_TO_VALUE.keys()))
            disp = None
            for k, v_mode in SAMPLE_DISPLAY_TO_VALUE.items():
                if v_mode == smode:
                    disp = k
                    break
            cmb_smode.setCurrentText(disp or "单像素")

            sp_srad = QSpinBox(block)
            sp_srad.setRange(0, 50)
            sp_srad.setValue(srad)

            sample_h.addWidget(cmb_smode)
            sample_h.addSpacing(4)
            sample_h.addWidget(QLabel("半径", sample_widget))
            sample_h.addWidget(sp_srad)
            sample_h.addStretch(1)

            form_sample.addRow("采样", sample_widget)
            v.addLayout(form_sample)

            # 行6：取色 + 测试 按钮一行
            btn_row = QWidget(block)
            btn_h = QHBoxLayout(btn_row)
            btn_h.setContentsMargins(0, 0, 0, 0)
            btn_h.setSpacing(4)

            btn_pick = QPushButton("取色", block)
            btn_test = QPushButton("测试", block)
            btn_h.addWidget(btn_pick)
            btn_h.addWidget(btn_test)
            btn_h.addStretch(1)
            v.addWidget(btn_row)

            self._ammo_stages_layout.addWidget(block)

            row_index = len(self._ammo_stage_rows)
            self._ammo_stage_rows.append(
                {
                    "charges": sp_charges,
                    "monitor": cmb_mon,
                    "x": sp_x,
                    "y": sp_y,
                    "r": sp_r,
                    "g": sp_g,
                    "b": sp_b,
                    "tol": sp_tol,
                    "sample_mode": cmb_smode,
                    "sample_radius": sp_srad,
                    "btn_pick": btn_pick,
                    "btn_test": btn_test,
                }
            )

        # 控件变更 -> 脏
        def _row_changed(*_args):
            if self._building_form:
                return
            self._apply_timer.start(200)

        for idx, row in enumerate(self._ammo_stage_rows):
            row["charges"].valueChanged.connect(_row_changed)
            row["monitor"].currentTextChanged.connect(_row_changed)
            row["x"].valueChanged.connect(_row_changed)
            row["y"].valueChanged.connect(_row_changed)
            row["r"].valueChanged.connect(_row_changed)
            row["g"].valueChanged.connect(_row_changed)
            row["b"].valueChanged.connect(_row_changed)
            row["tol"].valueChanged.connect(_row_changed)
            row["sample_mode"].currentTextChanged.connect(_row_changed)
            row["sample_radius"].valueChanged.connect(_row_changed)

            row["btn_pick"].clicked.connect(lambda _=None, i=idx: self._pick_ammo_stage_pixel(i))
            row["btn_test"].clicked.connect(lambda _=None, i=idx: self._test_ammo_stage_pixel(i))

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

    # ---------- 主像素 取色 / 测试 ----------

    def request_pick_current(self) -> None:
        """
        从当前技能发起取色（主像素）：
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

    # ---------- 弹药阶段 取色 / 测试 ----------

    def _pick_ammo_stage_pixel(self, row_index: int) -> None:
        """
        使用屏幕取色设置指定弹药阶段的像素（位置+颜色）。
        - 重用主像素的 start_pick 流程，但 on_confirm 写回阶段行控件。
        """
        if row_index < 0 or row_index >= len(self._ammo_stage_rows):
            return

        if not self.current_id:
            self._notify.error("请先选择一个技能")
            return

        if not self._apply_form_to_current(auto_save=False):
            return

        sid = self.current_id
        row = self._ammo_stage_rows[row_index]

        monitor = (row["monitor"].currentText() or "primary").strip() or "primary"
        sample_mode_disp = row["sample_mode"].currentText()
        sample_mode = SAMPLE_DISPLAY_TO_VALUE.get(sample_mode_disp, "single")
        sample_radius = int(row["sample_radius"].value())

        def _on_confirm(c) -> None:
            try:
                vx = int(c.vx)
                vy = int(c.vy)
            except Exception:
                vx = int(row["x"].value())
                vy = int(row["y"].value())

            row["x"].setValue(vx)
            row["y"].setValue(vy)
            row["r"].setValue(int(c.r))
            row["g"].setValue(int(c.g))
            row["b"].setValue(int(c.b))

            try:
                self._apply_form_to_current(auto_save=False)
                self.update_tree_row(sid)
            except Exception:
                log.exception("SkillsPage._pick_ammo_stage_pixel: apply/update failed")

            if getattr(c, "hex", ""):
                self._notify.status_msg(f"弹药阶段像素已应用: {c.hex}", ttl_ms=2000)

        self._start_pick(
            record_type="skill_pixel",      # 复用已有类型
            record_id=sid,
            sample_mode=sample_mode,
            sample_radius=sample_radius,
            monitor=monitor,
            on_confirm=_on_confirm,
        )

    def _test_ammo_stage_pixel(self, row_index: int) -> None:
        """
        基于当前阶段像素配置，从屏幕采样并与配置色+容差比较。
        """
        if row_index < 0 or row_index >= len(self._ammo_stage_rows):
            return

        if not self.current_id:
            self._notify.error("请先选择一个技能")
            return

        if not self._apply_form_to_current(auto_save=False):
            return

        row = self._ammo_stage_rows[row_index]
        monitor = (row["monitor"].currentText() or "primary").strip() or "primary"

        vx = int(row["x"].value())
        vy = int(row["y"].value())
        r_exp = int(row["r"].value())
        g_exp = int(row["g"].value())
        b_exp = int(row["b"].value())
        tol = int(row["tol"].value())

        sample_mode_disp = row["sample_mode"].currentText()
        sample_mode = SAMPLE_DISPLAY_TO_VALUE.get(sample_mode_disp, "single")
        sample_radius = int(row["sample_radius"].value())

        from core.pick.capture import SampleSpec

        sample = SampleSpec(
            mode=sample_mode,
            radius=sample_radius,
        )

        try:
            r_cur, g_cur, b_cur = self._cap.get_rgb_scoped_abs(
                x_abs=int(vx),
                y_abs=int(vy),
                sample=sample,
                monitor_key=monitor,
                require_inside=False,
            )
        except Exception as e:
            self._notify.error("测试弹药阶段像素失败", detail=str(e))
            return

        diff_r = abs(r_cur - r_exp)
        diff_g = abs(g_cur - g_exp)
        diff_b = abs(b_cur - b_exp)
        max_diff = max(diff_r, diff_g, diff_b)

        measured_hex = rgb_to_hex(r_cur, g_cur, b_cur)
        expected_hex = rgb_to_hex(r_exp, g_exp, b_exp)

        if max_diff <= tol:
            self._notify.info(
                f"阶段像素测试通过：当前 {measured_hex}，期望 {expected_hex}，最大通道差 {max_diff} ≤ 容差 {tol}"
            )
        else:
            self._notify.error(
                "阶段像素测试未通过",
                detail=(
                    f"当前 {measured_hex}，期望 {expected_hex}，"
                    f"最大通道差 {max_diff} > 容差 {tol}"
                ),
            )