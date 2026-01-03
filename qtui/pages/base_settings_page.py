# qtui/pages/base_settings_page.py
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
    QCheckBox,
    QPushButton,
    QFormLayout,
    QStyle,
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


class BaseSettingsPage(QWidget):
    """
    基础配置页面（Qt 版）：
    - 绑定 AppServices.base（BaseSettingsService）
    - 表单变更会防抖 200ms 调用 apply_patch
    - “保存”按钮调用 save_cmd
    - “重新加载”按钮调用 reload_cmd
    - 通过 ProfileSession.subscribe_dirty 显示“未保存*”
    - 取色确认热键使用 HotkeyEdit 录制
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

        # 订阅 dirty 状态 —— 使用 ProfileSession
        try:
            self._services.session.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

    # ---------- UI 构建 ----------

    def _init_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)

        # header
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

        # 三个分组
        g_ui = QGroupBox("界面 / 截图 / 取色确认", self)
        g_pick = QGroupBox("取色避让 / 预览 / 鼠标避让", self)
        g_io = QGroupBox("保存策略", self)

        vbox.addWidget(g_ui)
        vbox.addWidget(g_pick)
        vbox.addWidget(g_io)

        # group: UI / capture / confirm
        form_ui = QFormLayout(g_ui)

        # 主题
        self.cmb_theme = QComboBox(g_ui)
        themes = DARK_THEMES + ["---"] + LIGHT_THEMES
        self.cmb_theme.addItems(themes)
        form_ui.addRow("主题", self.cmb_theme)

        # 截图屏幕策略
        self.cmb_monitor = QComboBox(g_ui)
        self.cmb_monitor.addItems(list(_MONITOR_DISP_TO_VAL.keys()))
        form_ui.addRow("截图屏幕策略", self.cmb_monitor)

        # 取色确认热键（HotkeyEdit）
        self.hk_confirm = HotkeyEdit(g_ui, initial="f8")
        form_ui.addRow("取色确认热键", self.hk_confirm)

        hint = QLabel("提示：Esc 固定为取消", g_ui)
        form_ui.addRow("", hint)

        # group: pick avoidance / preview / mouse avoidance
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

        # 分隔
        form_pick.addRow(QLabel("", g_pick), QLabel("", g_pick))

        self.chk_mouse_avoid = QCheckBox(
            "确认取色前鼠标避让（防止 hover 高亮污染颜色）", g_pick
        )
        form_pick.addRow("", self.chk_mouse_avoid)

        self.spin_mouse_avoid_offset_y = QSpinBox(g_pick)
        self.spin_mouse_avoid_offset_y.setRange(0, 500)
        self.spin_mouse_avoid_offset_y.setSingleStep(5)
        form_pick.addRow("避让 Y 偏移(px)", self.spin_mouse_avoid_offset_y)

        self.spin_mouse_avoid_settle_ms = QSpinBox(g_pick)
        self.spin_mouse_avoid_settle_ms.setRange(0, 500)
        self.spin_mouse_avoid_settle_ms.setSingleStep(10)
        form_pick.addRow("避让后等待(ms)", self.spin_mouse_avoid_settle_ms)

        # group: IO
        form_io = QFormLayout(g_io)

        self.chk_auto_save = QCheckBox("自动保存（CRUD 时生效）", g_io)
        self.chk_backup = QCheckBox("保存时生成 .bak 备份", g_io)

        form_io.addRow(self.chk_auto_save)
        form_io.addRow(self.chk_backup)

        # buttons
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

        # 信号连接
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
        """
        当 profile 切换时，从新的 ctx.base 填充 UI。
        """
        self._ctx = ctx
        b = ctx.base
        self._building = True
        try:
            # 主题
            theme = b.ui.theme or "darkly"
            idx = self.cmb_theme.findText(theme)
            if idx < 0:
                idx = self.cmb_theme.findText("darkly")
            if idx >= 0:
                self.cmb_theme.setCurrentIndex(idx)

            # 截图策略
            disp = _MONITOR_VAL_TO_DISP.get(b.capture.monitor_policy, "主屏")
            idx = self.cmb_monitor.findText(disp)
            if idx >= 0:
                self.cmb_monitor.setCurrentIndex(idx)

            # 热键
            hk = getattr(b.pick, "confirm_hotkey", "") or "f8"
            self.hk_confirm.set_hotkey(hk)

            # 避让/预览
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

            # 鼠标避让
            self.chk_mouse_avoid.setChecked(bool(getattr(b.pick, "mouse_avoid", True)))
            self.spin_mouse_avoid_offset_y.setValue(int(getattr(b.pick, "mouse_avoid_offset_y", 80)))
            self.spin_mouse_avoid_settle_ms.setValue(int(getattr(b.pick, "mouse_avoid_settle_ms", 80)))

            # IO
            self.chk_auto_save.setChecked(bool(b.io.auto_save))
            self.chk_backup.setChecked(bool(b.io.backup_on_save))
        finally:
            self._building = False

        self._validate_confirm_hotkey_live()

    # ---------- 收集 patch ----------

    def _collect_patch(self) -> BaseSettingsPatch:
        theme = (self.cmb_theme.currentText() or "").strip()
        if theme == "---":
            theme = "darkly"

        monitor_policy = _MONITOR_DISP_TO_VAL.get(self.cmb_monitor.currentText(), "primary")

        avoid_mode = _AVOID_DISP_TO_VAL.get(self.cmb_avoid_mode.currentText(), "hide_main")
        preview_anchor = _ANCHOR_DISP_TO_VAL.get(self.cmb_preview_anchor.currentText(), "bottom_right")

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
            mouse_avoid_offset_y=clamp_int(int(self.spin_mouse_avoid_offset_y.value()), 0, 500),
            mouse_avoid_settle_ms=clamp_int(int(self.spin_mouse_avoid_settle_ms.value()), 0, 500),
            auto_save=bool(self.chk_auto_save.isChecked()),
            backup_on_save=bool(self.chk_backup.isChecked()),
        )

    # ---------- 热键校验 ----------

    def _clear_hotkey_error(self) -> None:
        self.hk_confirm.clear_error()

    def _apply_hotkey_error(self, msg: str) -> None:
        s = (msg or "").strip()
        self.hk_confirm.set_error(s)

    def _validate_confirm_hotkey_live(self) -> None:
        try:
            patch = self._collect_patch()
            self._services.base.validate_patch(patch)
            self._clear_hotkey_error()
        except Exception as e:
            self._apply_hotkey_error(str(e))

    # ---------- 防抖应用 ----------

    def _install_dirty_watchers(self) -> None:
        """
        给所有控件的变更信号连接到统一回调。
        """
        def on_any_changed(*_args) -> None:
            if self._building:
                return
            self._validate_confirm_hotkey_live()
            self._apply_timer.start(200)

        # combobox / spinbox / checkbox
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

    def _apply_now(self) -> None:
        if self._building:
            return
        patch = self._collect_patch()
        try:
            self._services.base.apply_patch(patch)
        except Exception:
            # 验证错误等已在 live 校验中提示，这里忽略
            pass

    # ---------- 按钮动作 ----------

    def _on_save(self) -> None:
        patch = self._collect_patch()
        try:
            saved = self._services.base.save_cmd(patch)
            if not saved:
                self._notify.status_msg("未检测到更改", ttl_ms=2000)
                return

            # 立即应用主题
            self._notify.apply_theme(self._services.profile.base.ui.theme)
            self._notify.info("profile.json 已保存（基础配置）")
        except Exception as e:
            self._apply_hotkey_error(str(e))
            self._notify.error("保存失败", detail=str(e))

    def _on_reload(self) -> None:
        try:
            self._services.base.reload_cmd()
            self.set_context(self._services.ctx)
            self._notify.apply_theme(self._services.profile.base.ui.theme)
            self._notify.info("已重新加载基础配置")
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))

    # ---------- 提供给 UnsavedGuard 的统一接口 ----------

    def flush_to_model(self) -> None:
        """
        供 UnsavedGuard 调用：强制把当前表单状态写入 profile.base。
        """
        try:
            self._apply_now()
        except Exception:
            pass