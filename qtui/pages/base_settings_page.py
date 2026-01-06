from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QFormLayout,
    QStyle,
    QLineEdit,
    QInputDialog,
)
from PySide6.QtCore import QTimer

from core.profiles import ProfileContext
from core.models.common import clamp_int
from core.app.services.base_settings_service import BaseSettingsPatch
from core.app.services.app_services import AppServices

from qtui.notify import UiNotify
from qtui.theme import DARK_THEMES, LIGHT_THEMES
from qtui.widgets.hotkey_edit import HotkeyEdit
from qtui.icons import load_icon

import logging

log = logging.getLogger(__name__)

_MONITOR_DISP_TO_VAL = {
    "主屏": "primary",
    "全部屏幕": "all",
    "屏幕1": "monitor_1",
    "屏幕2": "monitor_2",
}
_MONITOR_VAL_TO_DISP = {v: k for k, v in _MONITOR_DISP_TO_VAL.items()}

_AVOID_DISP_TO_VAL = {
    "隐藏主窗口": "hide_main",
    "最小化": "minimize",
    "移到角落": "move_aside",
    "不避让": "none",
}
_AVOID_VAL_TO_DISP = {v: k for k, v in _AVOID_DISP_TO_VAL.items()}

_ANCHOR_DISP_TO_VAL = {
    "右下": "bottom_right",
    "左下": "bottom_left",
    "右上": "top_right",
    "左上": "top_left",
}
_ANCHOR_VAL_TO_DISP = {v: k for k, v in _ANCHOR_DISP_TO_VAL.items()}

_START_SIGNAL_DISP_TO_VAL = {
    "技能像素变化（pixel）": "pixel",
    "施法条变化（cast_bar）": "cast_bar",
    "不检测直接开始（none）": "none",
}
_START_SIGNAL_VAL_TO_DISP = {v: k for k, v in _START_SIGNAL_DISP_TO_VAL.items()}


class BaseSettingsPage(QWidget):
    """
    基础配置页面（Qt 版）
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        services: AppServices,
        notify: UiNotify,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if services is None:
            raise RuntimeError("BaseSettingsPage requires services (cannot be None)")

        self._ctx = ctx
        self._services = services
        self._notify = notify

        self._building = False
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.timeout.connect(self._apply_now)

        self._init_ui()
        self.set_context(ctx)

        try:
            self._services.session.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

    # ---------- UI 构建 ----------

    def _init_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)

        header = QHBoxLayout()
        lbl_title = QLabel("基础配置", self)
        f = lbl_title.font()
        f.setPointSize(16)
        f.setBold(True)
        lbl_title.setFont(f)
        header.addWidget(lbl_title)

        header.addStretch(1)
        self._lbl_dirty = QLabel("", self)
        header.addWidget(self._lbl_dirty)

        vbox.addLayout(header)

        cols = QHBoxLayout()
        cols.setSpacing(10)
        vbox.addLayout(cols, 1)

        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        cols.addLayout(left_col, 1)
        cols.addLayout(right_col, 1)

        # ---- 左列：界面 / 截图 / 取色确认 ----
        g_ui = QGroupBox("界面 / 截图 / 取色确认", self)
        form_ui = QFormLayout(g_ui)

        self.cmb_theme = QComboBox(g_ui)
        themes = DARK_THEMES + ["---"] + LIGHT_THEMES
        self.cmb_theme.addItems(themes)
        form_ui.addRow("主题", self.cmb_theme)

        self.cmb_monitor = QComboBox(g_ui)
        self.cmb_monitor.addItems(list(_MONITOR_DISP_TO_VAL.keys()))
        form_ui.addRow("截图屏幕策略", self.cmb_monitor)

        self.hk_confirm = HotkeyEdit(g_ui, initial="f8")
        form_ui.addRow("取色确认热键", self.hk_confirm)

        hint = QLabel("提示：Esc 固定为取消", g_ui)
        form_ui.addRow("", hint)

        left_col.addWidget(g_ui)

        g_pick = QGroupBox("取色避让 / 预览 / 鼠标避让", self)
        form_pick = QFormLayout(g_pick)

        self.cmb_avoid_mode = QComboBox(g_pick)
        self.cmb_avoid_mode.addItems(list(_AVOID_DISP_TO_VAL.keys()))
        form_pick.addRow("窗口避让模式", self.cmb_avoid_mode)

        self.spin_avoid_delay = QSpinBox(g_pick)
        self.spin_avoid_delay.setRange(0, 5000)
        self.spin_avoid_delay.setSingleStep(10)
        form_pick.addRow("进入延迟(ms)", self.spin_avoid_delay)

        self.chk_preview_follow = QCheckBox("预览跟随鼠标", g_pick)
        form_pick.addRow("", self.chk_preview_follow)

        self.spin_preview_offset_x = QSpinBox(g_pick)
        self.spin_preview_offset_x.setRange(-500, 500)
        self.spin_preview_offset_x.setSingleStep(1)
        form_pick.addRow("预览偏移 X", self.spin_preview_offset_x)

        self.spin_preview_offset_y = QSpinBox(g_pick)
        self.spin_preview_offset_y.setRange(-500, 500)
        self.spin_preview_offset_y.setSingleStep(1)
        form_pick.addRow("预览偏移 Y", self.spin_preview_offset_y)

        self.cmb_preview_anchor = QComboBox(g_pick)
        self.cmb_preview_anchor.addItems(list(_ANCHOR_DISP_TO_VAL.keys()))
        form_pick.addRow("预览锚点", self.cmb_preview_anchor)

        form_pick.addRow(QLabel("", g_pick), QLabel("", g_pick))

        self.chk_mouse_avoid = QCheckBox("确认取色前鼠标避让（防止 hover 高亮污染颜色）", g_pick)
        form_pick.addRow("", self.chk_mouse_avoid)

        self.spin_mouse_avoid_offset_y = QSpinBox(g_pick)
        self.spin_mouse_avoid_offset_y.setRange(-500, 500)
        self.spin_mouse_avoid_offset_y.setSingleStep(5)
        form_pick.addRow("避让 Y 偏移(px)", self.spin_mouse_avoid_offset_y)

        self.spin_mouse_avoid_settle_ms = QSpinBox(g_pick)
        self.spin_mouse_avoid_settle_ms.setRange(0, 500)
        self.spin_mouse_avoid_settle_ms.setSingleStep(10)
        form_pick.addRow("避让后等待(ms)", self.spin_mouse_avoid_settle_ms)

        left_col.addWidget(g_pick)

        # ---- 右列：施法完成 / 执行策略 ----
        g_cast = QGroupBox("施法完成 / 执行策略", self)
        form_cast = QFormLayout(g_cast)

        self.cmb_cast_mode = QComboBox(g_cast)
        self.cmb_cast_mode.addItems(["仅按技能读条时间", "使用施法条像素判断"])
        form_cast.addRow("施法完成模式", self.cmb_cast_mode)

        row_cast_point = QHBoxLayout()
        self.txt_cast_point_id = QLineEdit(g_cast)
        self.txt_cast_point_id.setPlaceholderText("施法条点位 ID（来自“取色点位配置”）")
        btn_select_point = QPushButton("选择...", g_cast)
        btn_select_point.clicked.connect(self._on_select_cast_point)
        row_cast_point.addWidget(self.txt_cast_point_id, 1)
        row_cast_point.addWidget(btn_select_point)
        form_cast.addRow("施法条点位 ID", row_cast_point)

        self.spin_cast_tol = QSpinBox(g_cast)
        self.spin_cast_tol.setRange(0, 255)
        self.spin_cast_tol.setSingleStep(1)
        self.spin_cast_tol.setValue(15)
        form_cast.addRow("施法条颜色容差", self.spin_cast_tol)

        self.spin_cast_poll = QSpinBox(g_cast)
        self.spin_cast_poll.setRange(10, 1000)
        self.spin_cast_poll.setSingleStep(5)
        form_cast.addRow("施法条轮询间隔(ms)", self.spin_cast_poll)

        self.spin_cast_max_factor = QDoubleSpinBox(g_cast)
        self.spin_cast_max_factor.setRange(0.1, 10.0)
        self.spin_cast_max_factor.setSingleStep(0.1)
        self.spin_cast_max_factor.setDecimals(2)
        form_cast.addRow("施法条最长等待倍数", self.spin_cast_max_factor)

        # 执行启停热键
        self.chk_exec_hotkey = QCheckBox("启用执行启停热键", g_cast)
        form_cast.addRow(self.chk_exec_hotkey)

        self.hk_exec_toggle = HotkeyEdit(g_cast, initial="f9")
        form_cast.addRow("启停热键", self.hk_exec_toggle)

        self.spin_exec_skill_gap = QSpinBox(g_cast)
        self.spin_exec_skill_gap.setRange(0, 10**6)
        self.spin_exec_skill_gap.setSingleStep(10)
        form_cast.addRow("技能间默认间隔(ms)", self.spin_exec_skill_gap)

        # -------- 新增：状态机/轮询/重试 --------
        self.spin_exec_poll_not_ready = QSpinBox(g_cast)
        self.spin_exec_poll_not_ready.setRange(10, 10**6)
        self.spin_exec_poll_not_ready.setSingleStep(10)
        form_cast.addRow("not_ready 轮询间隔(ms)", self.spin_exec_poll_not_ready)

        self.cmb_start_signal = QComboBox(g_cast)
        self.cmb_start_signal.addItems(list(_START_SIGNAL_DISP_TO_VAL.keys()))
        form_cast.addRow("开始施法信号", self.cmb_start_signal)

        self.spin_start_timeout = QSpinBox(g_cast)
        self.spin_start_timeout.setRange(1, 10**6)
        self.spin_start_timeout.setSingleStep(5)
        form_cast.addRow("开始判定超时(ms)", self.spin_start_timeout)

        self.spin_start_poll = QSpinBox(g_cast)
        self.spin_start_poll.setRange(5, 10**6)
        self.spin_start_poll.setSingleStep(5)
        form_cast.addRow("开始判定轮询(ms)", self.spin_start_poll)

        self.spin_max_retries = QSpinBox(g_cast)
        self.spin_max_retries.setRange(0, 1000)
        self.spin_max_retries.setSingleStep(1)
        form_cast.addRow("最大重试次数", self.spin_max_retries)

        self.spin_retry_gap = QSpinBox(g_cast)
        self.spin_retry_gap.setRange(0, 10**6)
        self.spin_retry_gap.setSingleStep(10)
        form_cast.addRow("重试间隔(ms)", self.spin_retry_gap)

        right_col.addWidget(g_cast)

        g_io = QGroupBox("保存策略", self)
        form_io = QFormLayout(g_io)

        self.chk_auto_save = QCheckBox("自动保存（CRUD 时生效）", g_io)
        self.chk_backup = QCheckBox("保存时生成 .bak 备份", g_io)
        form_io.addRow(self.chk_auto_save)
        form_io.addRow(self.chk_backup)

        right_col.addWidget(g_io)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        style = self.style()
        icon_save = load_icon("save", style, QStyle.StandardPixmap.SP_DialogSaveButton)
        icon_reload = load_icon("reload", style, QStyle.StandardPixmap.SP_BrowserReload)

        self.btn_reload = QPushButton("重新加载(放弃未保存)", self)
        self.btn_reload.setIcon(icon_reload)
        btn_row.addWidget(self.btn_reload)

        self.btn_save = QPushButton("保存", self)
        self.btn_save.setIcon(icon_save)
        btn_row.addWidget(self.btn_save)

        vbox.addLayout(btn_row)

        self.btn_save.clicked.connect(self._on_save)
        self.btn_reload.clicked.connect(self._on_reload)

        self._install_dirty_watchers()

    # ---------- 脏状态 ----------
    def _on_store_dirty(self, parts) -> None:
        try:
            parts_set = set(parts or [])
        except Exception:
            parts_set = set()
        self._lbl_dirty.setText("未保存*" if "base" in parts_set else "")

    # ---------- 数据绑定 ----------
    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        b = ctx.base
        self._building = True
        try:
            theme = b.ui.theme or "darkly"
            idx = self.cmb_theme.findText(theme)
            if idx < 0:
                idx = self.cmb_theme.findText("darkly")
            if idx >= 0:
                self.cmb_theme.setCurrentIndex(idx)

            disp = _MONITOR_VAL_TO_DISP.get(b.capture.monitor_policy, "主屏")
            idx = self.cmb_monitor.findText(disp)
            if idx >= 0:
                self.cmb_monitor.setCurrentIndex(idx)

            hk = getattr(b.pick, "confirm_hotkey", "") or "f8"
            self.hk_confirm.set_hotkey(hk)

            av = b.pick.avoidance
            disp_mode = _AVOID_VAL_TO_DISP.get(av.mode, "隐藏主窗口")
            idx = self.cmb_avoid_mode.findText(disp_mode)
            if idx >= 0:
                self.cmb_avoid_mode.setCurrentIndex(idx)

            self.spin_avoid_delay.setValue(int(av.delay_ms))
            self.chk_preview_follow.setChecked(bool(av.preview_follow_cursor))
            self.spin_preview_offset_x.setValue(int(av.preview_offset[0]))
            self.spin_preview_offset_y.setValue(int(av.preview_offset[1]))
            disp_anchor = _ANCHOR_VAL_TO_DISP.get(av.preview_anchor, "右下")
            idx = self.cmb_preview_anchor.findText(disp_anchor)
            if idx >= 0:
                self.cmb_preview_anchor.setCurrentIndex(idx)

            self.chk_mouse_avoid.setChecked(bool(getattr(b.pick, "mouse_avoid", True)))
            self.spin_mouse_avoid_offset_y.setValue(int(getattr(b.pick, "mouse_avoid_offset_y", 80)))
            self.spin_mouse_avoid_settle_ms.setValue(int(getattr(b.pick, "mouse_avoid_settle_ms", 80)))

            self.chk_auto_save.setChecked(bool(b.io.auto_save))
            self.chk_backup.setChecked(bool(b.io.backup_on_save))

            cb = getattr(b, "cast_bar", None)
            mode = (getattr(cb, "mode", "timer") or "timer").strip().lower() if cb is not None else "timer"
            pid = getattr(cb, "point_id", "") or "" if cb is not None else ""
            tol = int(getattr(cb, "tolerance", 15) or 15) if cb is not None else 15
            poll = int(getattr(cb, "poll_interval_ms", 30) or 30) if cb is not None else 30
            factor = float(getattr(cb, "max_wait_factor", 1.5) or 1.5) if cb is not None else 1.5

            self.cmb_cast_mode.setCurrentText("使用施法条像素判断" if mode == "bar" else "仅按技能读条时间")
            self.txt_cast_point_id.setText(pid)
            self.spin_cast_tol.setValue(int(tol))
            self.spin_cast_poll.setValue(int(max(10, min(1000, poll))))
            self.spin_cast_max_factor.setValue(float(max(0.1, min(10.0, factor))))

            ex = getattr(b, "exec", None)
            enabled = bool(getattr(ex, "enabled", False)) if ex is not None else False
            hk_exec = getattr(ex, "toggle_hotkey", "") or "" if ex is not None else ""
            gap = int(getattr(ex, "default_skill_gap_ms", 50) or 50) if ex is not None else 50

            self.chk_exec_hotkey.setChecked(bool(enabled))
            self.hk_exec_toggle.set_hotkey(hk_exec or "f9")
            self.spin_exec_skill_gap.setValue(int(max(0, gap)))

            # 新增字段加载
            poll_not_ready = int(getattr(ex, "poll_not_ready_ms", 50) or 50) if ex is not None else 50
            start_mode = (getattr(ex, "start_signal_mode", "pixel") or "pixel").strip().lower() if ex is not None else "pixel"
            start_timeout = int(getattr(ex, "start_timeout_ms", 20) or 20) if ex is not None else 20
            start_poll = int(getattr(ex, "start_poll_ms", 10) or 10) if ex is not None else 10
            max_retries = int(getattr(ex, "max_retries", 3) or 3) if ex is not None else 3
            retry_gap = int(getattr(ex, "retry_gap_ms", 30) or 30) if ex is not None else 30

            self.spin_exec_poll_not_ready.setValue(int(max(10, poll_not_ready)))

            disp_sig = _START_SIGNAL_VAL_TO_DISP.get(start_mode, "技能像素变化（pixel）")
            idx = self.cmb_start_signal.findText(disp_sig)
            if idx >= 0:
                self.cmb_start_signal.setCurrentIndex(idx)

            self.spin_start_timeout.setValue(int(max(1, start_timeout)))
            self.spin_start_poll.setValue(int(max(5, start_poll)))
            self.spin_max_retries.setValue(int(max(0, max_retries)))
            self.spin_retry_gap.setValue(int(max(0, retry_gap)))

        finally:
            self._building = False

    # ---------- 收集 patch ----------
    def _collect_patch(self) -> BaseSettingsPatch:
        theme = (self.cmb_theme.currentText() or "").strip()
        if theme == "---":
            theme = "darkly"

        monitor_policy = _MONITOR_DISP_TO_VAL.get(self.cmb_monitor.currentText(), "primary")

        avoid_mode = _AVOID_DISP_TO_VAL.get(self.cmb_avoid_mode.currentText(), "hide_main")
        preview_anchor = _ANCHOR_VAL_TO_DISP.get(self.cmb_preview_anchor.currentText(), "bottom_right")

        cast_mode_disp = self.cmb_cast_mode.currentText()
        cast_mode = "timer" if cast_mode_disp.startswith("仅按") else "bar"

        exec_toggle_enabled = bool(self.chk_exec_hotkey.isChecked())
        exec_toggle_hotkey = self.hk_exec_toggle.get_hotkey().strip()

        start_sig_disp = self.cmb_start_signal.currentText()
        start_sig_val = _START_SIGNAL_DISP_TO_VAL.get(start_sig_disp, "pixel")

        return BaseSettingsPatch(
            theme=theme or "darkly",
            monitor_policy=monitor_policy,

            pick_confirm_hotkey=self.hk_confirm.get_hotkey().strip(),

            avoid_mode=avoid_mode,
            avoid_delay_ms=clamp_int(int(self.spin_avoid_delay.value()), 0, 5000),
            preview_follow=bool(self.chk_preview_follow.isChecked()),
            preview_offset_x=int(self.spin_preview_offset_x.value()),
            preview_offset_y=int(self.spin_preview_offset_y.value()),
            preview_anchor=preview_anchor,

            mouse_avoid=bool(self.chk_mouse_avoid.isChecked()),
            mouse_avoid_offset_y=clamp_int(int(self.spin_mouse_avoid_offset_y.value()), -500, 500),
            mouse_avoid_settle_ms=clamp_int(int(self.spin_mouse_avoid_settle_ms.value()), 0, 500),

            auto_save=bool(self.chk_auto_save.isChecked()),
            backup_on_save=bool(self.chk_backup.isChecked()),

            cast_mode=cast_mode,
            cast_bar_point_id=self.txt_cast_point_id.text(),
            cast_bar_tolerance=int(self.spin_cast_tol.value()),
            cast_bar_poll_interval_ms=int(self.spin_cast_poll.value()),
            cast_bar_max_wait_factor=float(self.spin_cast_max_factor.value()),

            exec_toggle_enabled=exec_toggle_enabled,
            exec_toggle_hotkey=exec_toggle_hotkey,
            exec_skill_gap_ms=int(self.spin_exec_skill_gap.value()),

            exec_poll_not_ready_ms=int(self.spin_exec_poll_not_ready.value()),
            exec_start_signal_mode=start_sig_val,
            exec_start_timeout_ms=int(self.spin_start_timeout.value()),
            exec_start_poll_ms=int(self.spin_start_poll.value()),
            exec_max_retries=int(self.spin_max_retries.value()),
            exec_retry_gap_ms=int(self.spin_retry_gap.value()),
        )

    # ---------- 防抖应用 ----------
    def _install_dirty_watchers(self) -> None:
        def on_any_changed(*_args) -> None:
            if self._building:
                return
            self._apply_timer.start(200)

        # 绑定所有控件
        self.cmb_theme.currentTextChanged.connect(on_any_changed)
        self.cmb_monitor.currentTextChanged.connect(on_any_changed)
        self.hk_confirm.hotkeyChanged.connect(on_any_changed)

        self.cmb_avoid_mode.currentTextChanged.connect(on_any_changed)
        self.spin_avoid_delay.valueChanged.connect(on_any_changed)
        self.chk_preview_follow.toggled.connect(on_any_changed)
        self.spin_preview_offset_x.valueChanged.connect(on_any_changed)
        self.spin_preview_offset_y.valueChanged.connect(on_any_changed)
        self.cmb_preview_anchor.currentTextChanged.connect(on_any_changed)

        self.chk_mouse_avoid.toggled.connect(on_any_changed)
        self.spin_mouse_avoid_offset_y.valueChanged.connect(on_any_changed)
        self.spin_mouse_avoid_settle_ms.valueChanged.connect(on_any_changed)

        self.chk_auto_save.toggled.connect(on_any_changed)
        self.chk_backup.toggled.connect(on_any_changed)

        self.cmb_cast_mode.currentTextChanged.connect(on_any_changed)
        self.txt_cast_point_id.textChanged.connect(on_any_changed)
        self.spin_cast_tol.valueChanged.connect(on_any_changed)
        self.spin_cast_poll.valueChanged.connect(on_any_changed)
        self.spin_cast_max_factor.valueChanged.connect(on_any_changed)

        self.chk_exec_hotkey.toggled.connect(on_any_changed)
        self.hk_exec_toggle.hotkeyChanged.connect(on_any_changed)
        self.spin_exec_skill_gap.valueChanged.connect(on_any_changed)

        self.spin_exec_poll_not_ready.valueChanged.connect(on_any_changed)
        self.cmb_start_signal.currentTextChanged.connect(on_any_changed)
        self.spin_start_timeout.valueChanged.connect(on_any_changed)
        self.spin_start_poll.valueChanged.connect(on_any_changed)
        self.spin_max_retries.valueChanged.connect(on_any_changed)
        self.spin_retry_gap.valueChanged.connect(on_any_changed)

    def _apply_now(self) -> None:
        if self._building:
            return
        patch = self._collect_patch()
        try:
            self._services.base.apply_patch(patch)
        except Exception:
            # 防抖自动应用失败（例如校验错误）在显式保存时会提示用户；
            # 这里仅记录 debug 日志，避免静默吞掉调试信息。
            log.debug(
                "BaseSettingsPage._apply_now: apply_patch failed (ignored in debounced apply)",
                exc_info=True,
            )

    # ---------- 施法条点位选择 ----------
    def _on_select_cast_point(self) -> None:
        pts = list(getattr(self._ctx.points, "points", []) or [])
        if not pts:
            self._notify.error("当前 Profile 下没有点位，请先添加点位。")
            return

        items = [f"{p.name or '(未命名)'} [{(p.id or '')[-6:]}]" for p in pts]
        choice, ok = QInputDialog.getItem(self, "选择施法条点位", "请选择施法条所在的点位：", items, 0, False)
        if not ok:
            return

        try:
            idx = items.index(choice)
        except ValueError:
            idx = 0
        p = pts[idx]
        self.txt_cast_point_id.setText(p.id or "")

    # ---------- 按钮动作 ----------
    def _on_save(self) -> None:
        patch = self._collect_patch()
        try:
            saved = self._services.base.save_cmd(patch)
            if not saved:
                self._notify.status_msg("未检测到更改", ttl_ms=2000)
                return
            self._notify.info("profile.json 已保存（基础配置）")
        except Exception as e:
            self._notify.error("保存失败", detail=str(e))

    def _on_reload(self) -> None:
        try:
            self._services.base.reload_cmd()
            self.set_context(self._services.ctx)
            self._notify.info("已重新加载基础配置")
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))

    def flush_to_model(self) -> None:
        try:
            self._apply_now()
        except Exception:
            log.exception("BaseSettingsPage.flush_to_model: _apply_now failed")
