# qtui/main_window.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QIcon, QCloseEvent

import logging

from core.app.services.app_services import AppServices
from core.app.services.profile_service import ProfileService
from core.pick.capture import SampleSpec
from core.pick.models import PickSessionConfig
from core.profiles import ProfileContext

from qtui.dispatcher import QtDispatcher
from qtui.nav_panel import NavPanel
from qtui.notify import UiNotify
from qtui.pick.coordinator import QtPickCoordinator, UiPickPolicySnapshot
from qtui.profile_controller import ProfileController
from qtui.status_bar import StatusController
from qtui.theme import apply_theme
from qtui.window_state import WindowStateController
from qtui.unsaved_guard import UnsavedChangesGuard
from qtui.icons import load_icon, resource_path
from rotation_editor.ui.presets_page import RotationPresetsPage
from rotation_editor.ui.editor.main_page import RotationEditorPage

from qtui.exec_hotkey import ExecHotkeyController
from qtui.quick_exec_panel import QuickExecPanel

from qtui.extensions.gw2_skill_import_dialog import Gw2SkillImportDialog  # 新增：GW2 插件对话框

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Qt 版主窗口：

    - 左侧：NavPanel（Profile 区 + 页面导航，带图标）
    - 右侧：QStackedWidget（基础配置 / 技能配置 / 点位配置 / 循环方案管理 / 循环编辑器）
    - 底部：StatusController 封装的 QStatusBar
    - 服务层：AppServices / ProfileService / ProfileController
    - 取色：QtPickCoordinator + 预览窗，供 SkillsPage / PointsPage 使用
    - 几何：WindowStateController 负责记忆窗口大小/位置
    - 未保存变更：UnsavedChangesGuard 负责提示保存/放弃/取消
    - 插件 / 扩展：如 GW2 技能导入
    """

    def __init__(
        self,
        *,
        theme_name: str,
        profile_manager,
        profile_ctx: ProfileContext,
        app_state_repo,
        app_state,
    ) -> None:
        super().__init__()

        # 核心对象
        self._theme_name = theme_name
        self._pm = profile_manager
        self._ctx: ProfileContext = profile_ctx
        self._app_state_repo = app_state_repo
        self._app_state = app_state

        # 标题
        self._base_title = "激战2_协同学院_自动化克鲁"
        self.setWindowTitle(self._base_title)

        # 基础设施
        self.dispatcher = QtDispatcher(self)
        self.status = StatusController(self)
        self.notify = UiNotify(dispatcher=self.dispatcher, status=self.status)

        # 服务层（注意：AppServices 内部持有 ProfileSession）
        self.services = AppServices(
            ctx=self._ctx,
            notify_error=lambda m, d="": self.notify.error(m, detail=d),
        )
        self.profile_service = ProfileService(pm=self._pm, services=self.services)

        # 取色协调器
        self._pick_coord = QtPickCoordinator(
            root=self,
            dispatcher=self.dispatcher,
            status=self.status,
            ui_policy_provider=self._ui_policy_snapshot,
        )

        # 窗口几何控制
        self._win_state = WindowStateController(
            root=self,
            repo=self._app_state_repo,
            state=self._app_state,
        )

        # 未保存变更守卫（稍后在页面创建完成后实例化）
        self._guard: Optional[UnsavedChangesGuard] = None

        # Profile 控制器（guard_confirm 先用 wrapper 占位）
        self.profile_controller = ProfileController(
            window=self,
            profile_service=self.profile_service,
            apply_ctx_to_ui=self._apply_ctx_to_ui,
            refresh_profiles_ui=self._refresh_profiles_ui,
            guard_confirm=self._guard_confirm_wrapper,
            notify=self.notify,
        )

        # 执行启停热键控制器（初始化为 None，稍后在 _setup_central_widget 后创建）
        self._exec_hotkey: Optional[ExecHotkeyController] = None
        self._quick_panel: Optional[QuickExecPanel] = None

        # 脏状态标题“*”
        try:
            self.services.session.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

        # UI 布局
        self._setup_icon()
        self._setup_central_widget()

        # 实例化未保存变更守卫（此时页面已经创建）
        self._guard = UnsavedChangesGuard(
            window=self,
            services=self.services,
            pages_flush_all=self._flush_all_pages,
            pages_set_context=self._set_pages_context,
            backup_provider=lambda: bool(getattr(self._ctx.base.io, "backup_on_save", True)),
        )

        # 执行启停热键控制器：在页面创建完成后再初始化
        try:
            self._exec_hotkey = ExecHotkeyController(
                dispatcher=self.dispatcher,
                get_ctx=lambda: self._ctx,
                toggle_cb=self._toggle_exec_by_hotkey,
            )
        except Exception:
            self._exec_hotkey = None

        # 使用 WindowStateController 恢复窗口几何
        self._win_state.apply_initial_geometry()

        # 状态栏初始状态
        self.status.set_profile(self._ctx.profile_name)
        self.status.set_page("基础配置")
        self.status.set_status("ready")

        # Profile 下拉初始化
        self._refresh_profiles_ui(None)

    # ---------- UI 基本结构 ----------

    def _setup_icon(self) -> None:
        from pathlib import Path
        from qtui.icons import resource_path

        candidates = [
            resource_path("assets/icons/app.ico"),
            resource_path("assets/icons/profile.svg"),
            resource_path("assets/icons/profile.png"),
        ]
        for p in candidates:
            try:
                path_obj = Path(p)
                if path_obj.is_file():
                    self.setWindowIcon(QIcon(str(path_obj)))
                    break
            except Exception:
                continue

    def _setup_central_widget(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧导航
        self._nav = NavPanel(self)
        layout.addWidget(self._nav)

        # 右侧页面容器
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        from qtui.pages.base_settings_page import BaseSettingsPage
        from qtui.pages.skills_page import SkillsPage
        from qtui.pages.points_page import PointsPage

        self._page_indices: Dict[str, int] = {}

        # 三个实际页面
        self._page_base = BaseSettingsPage(
            ctx=self._ctx,
            services=self.services,
            notify=self.notify,
            parent=self,
        )
        self._page_skills = SkillsPage(
            ctx=self._ctx,
            services=self.services,
            notify=self.notify,
            start_pick=self._start_pick_for_record,
            parent=self,
        )
        self._page_points = PointsPage(
            ctx=self._ctx,
            services=self.services,
            notify=self.notify,
            start_pick=self._start_pick_for_record,
            parent=self,
        )

        # 循环/轨道方案管理页（rotation_editor）
        self._page_rotation = RotationPresetsPage(
            ctx=self._ctx,
            session=self.services.session,
            notify=self.notify,
            open_editor=self._open_rotation_editor,
            parent=self,
        )

        # 循环编辑器页（Mode/Track/Node 列表版）
        self._page_rotation_editor = RotationEditorPage(
            ctx=self._ctx,
            session=self.services.session,
            notify=self.notify,
            dispatcher=self.dispatcher,  # 将 QtDispatcher 作为 Scheduler 传给执行引擎
            parent=self,
        )

        self._page_indices["base"] = self._stack.addWidget(self._page_base)
        self._page_indices["skills"] = self._stack.addWidget(self._page_skills)
        self._page_indices["points"] = self._stack.addWidget(self._page_points)
        self._page_indices["rotation"] = self._stack.addWidget(self._page_rotation)
        self._page_indices["rotation_editor"] = self._stack.addWidget(self._page_rotation_editor)

        # 默认显示基础配置
        self._stack.setCurrentIndex(self._page_indices["base"])
        self._nav.set_active_page("base")

        # 快捷执行面板：初始创建并隐藏
        try:
            # 不再把 MainWindow 作为 parent，让它成为独立顶层窗口，
            # 这样主窗口最小化时，它不会跟着一起最小化。
            self._quick_panel = QuickExecPanel(
                ctx=self._ctx,
                engine_host=self._page_rotation_editor,
                open_editor_cb=self._open_rotation_editor,
                parent=None,
            )
            self._quick_panel.hide()
        except Exception:
            self._quick_panel = None

        # 信号连接
        self._nav.page_selected.connect(self._on_page_selected)
        self._nav.profile_selected.connect(self._on_profile_selected)
        self._nav.profile_action.connect(self._on_profile_action)
        self._nav.quick_exec_requested.connect(self._on_quick_exec_requested)
        self._nav.plugin_action.connect(self._on_plugin_action)  # 新增：插件入口

        self.setCentralWidget(central)

    # ---------- Profile 列表 UI ----------

    def _refresh_profiles_ui(self, select: Optional[str]) -> None:
        """
        用 ProfileManager 列出所有 profiles，并在 NavPanel 中刷新。
        """
        try:
            names = self._pm.list_profiles()
        except Exception:
            names = []
        if not names:
            names = ["Default"]

        current = select or self._ctx.profile_name or names[0]
        self._nav.set_profiles(names, current)

    # ---------- 脏状态标题 ----------

    def _on_store_dirty(self, parts) -> None:
        try:
            parts_set = set(parts or [])
        except Exception:
            parts_set = set()

        dirty = bool(parts_set)
        title = self._base_title + (" *" if dirty else "")
        if self.windowTitle() != title:
            self.setWindowTitle(title)

        # base 配置变化时刷新执行启停热键
        if self._exec_hotkey is not None and "base" in parts_set:
            try:
                self._exec_hotkey.refresh_from_ctx()
            except Exception:
                pass

    # ---------- 导航回调 ----------

    def _on_page_selected(self, key: str) -> None:
        idx = self._page_indices.get(key)
        if idx is None:
            self.notify.error(f"未知页面: {key}")
            return

        self._stack.setCurrentIndex(idx)
        self._nav.set_active_page(key)

        title_map = {
            "base": "基础配置",
            "skills": "技能配置",
            "points": "取色点位配置",
            "rotation": "循环/轨道方案",
            "rotation_editor": "循环编辑器",
        }
        page_title = title_map.get(key, key)
        self.status.set_page(page_title)
        self.status.status_msg("ready", ttl_ms=1000)

    def _on_profile_selected(self, name: str) -> None:
        """
        由 NavPanel 触发的 profile 选择。
        """
        self.profile_controller.on_select(name, self._ctx)

    def _on_profile_action(self, action: str) -> None:
        """
        由 NavPanel 触发的新建/复制/重命名/删除。
        """
        self.profile_controller.on_action(action, self._ctx)

    def _on_plugin_action(self, action: str) -> None:
        """
        来自 NavPanel 的插件/扩展操作。
        """
        action = (action or "").strip()
        if action == "gw2_skill_import":
            self._open_gw2_skill_import_dialog()
        else:
            self.notify.error(f"未知插件操作: {action}")

    # ---------- 应用新的 ProfileContext 到 UI ----------

    def _apply_ctx_to_ui(self, ctx: ProfileContext) -> None:
        """
        ProfileController 调用：
        - 更新当前 ctx
        - 更新状态栏中的 profile 名称
        - 更新 NavPanel 下拉
        - 重新应用主题
        - 通知各页面刷新上下文
        """
        self._ctx = ctx

        # 状态栏同步
        self.status.set_profile(ctx.profile_name)

        # 主题同步
        app = QApplication.instance()
        if app is not None:
            theme = ctx.base.ui.theme or "darkly"
            apply_theme(app, theme)
            self._theme_name = theme

        # 左侧下拉同步
        self._refresh_profiles_ui(ctx.profile_name)

        # 页面上下文同步
        self._set_pages_context(ctx)

        # 快捷执行面板同步 ProfileContext
        if hasattr(self, "_quick_panel") and self._quick_panel is not None:
            try:
                self._quick_panel.set_context(ctx)
            except Exception:
                pass

        # 执行启停热键同步
        if self._exec_hotkey is not None:
            try:
                self._exec_hotkey.refresh_from_ctx()
            except Exception:
                pass

    # ---------- 取色 UI 策略快照 ----------

    def _ui_policy_snapshot(self) -> UiPickPolicySnapshot:
        """
        从当前 ProfileContext 抽取取色相关的 UI 避让/预览策略快照。
        """
        b = self._ctx.base
        av = getattr(getattr(b, "pick", None), "avoidance", None)

        mode = "hide_main"
        preview_follow = True
        preview_offset = (30, 30)
        preview_anchor = "bottom_right"

        if av is not None:
            try:
                mode = (getattr(av, "mode", mode) or mode).strip()
            except Exception:
                pass
            try:
                preview_follow = bool(getattr(av, "preview_follow_cursor", preview_follow))
            except Exception:
                pass
            try:
                off = getattr(av, "preview_offset", preview_offset)
                ox = int(off[0])
                oy = int(off[1])
                preview_offset = (ox, oy)
            except Exception:
                pass
            try:
                preview_anchor = (getattr(av, "preview_anchor", preview_anchor) or preview_anchor).strip()
            except Exception:
                pass

        return UiPickPolicySnapshot(
            avoid_mode=mode or "hide_main",
            preview_follow=bool(preview_follow),
            preview_offset=preview_offset,
            preview_anchor=preview_anchor or "bottom_right",
        )

    # ---------- 取色入口（供 SkillsPage / PointsPage 调用） ----------

    def _start_pick_for_record(
        self,
        *,
        record_type: str,      # "skill_pixel" | "point"
        record_id: str,
        sample_mode: str,
        sample_radius: int,
        monitor: str,
        on_confirm,            # Callable[[PickConfirmed], None]
    ) -> None:
        """
        由 SkillsPage / PointsPage 调用，发起一次取色会话。
        """
        b = self._ctx.base

        # 采样配置
        sample = SampleSpec(
            mode=(sample_mode or "single").strip() or "single",
            radius=int(sample_radius),
        )

        # monitor 策略：记录自身配置优先，否则退回全局 capture.monitor_policy
        mon_req = (monitor or "").strip()
        if not mon_req:
            try:
                mon_req = (b.capture.monitor_policy or "primary").strip()
            except Exception:
                mon_req = "primary"
        if not mon_req:
            mon_req = "primary"

        # 避让/确认配置
        av = getattr(getattr(b, "pick", None), "avoidance", None)
        try:
            delay_ms = int(getattr(av, "delay_ms", 120) or 120)
        except Exception:
            delay_ms = 120

        try:
            confirm_hotkey = str(getattr(b.pick, "confirm_hotkey", "f8") or "f8")
        except Exception:
            confirm_hotkey = "f8"

        try:
            mouse_avoid = bool(getattr(b.pick, "mouse_avoid", True))
        except Exception:
            mouse_avoid = True

        try:
            mouse_avoid_offset_y = int(getattr(b.pick, "mouse_avoid_offset_y", 80) or 80)
        except Exception:
            mouse_avoid_offset_y = 80

        try:
            mouse_avoid_settle_ms = int(getattr(b.pick, "mouse_avoid_settle_ms", 80) or 80)
        except Exception:
            mouse_avoid_settle_ms = 80

        cfg = PickSessionConfig(
            record_type=record_type,
            record_id=record_id,
            monitor_requested=mon_req,
            sample=sample,
            delay_ms=delay_ms,
            preview_throttle_ms=30,
            error_throttle_ms=800,
            confirm_hotkey=confirm_hotkey,
            mouse_avoid=mouse_avoid,
            mouse_avoid_offset_y=mouse_avoid_offset_y,
            mouse_avoid_settle_ms=mouse_avoid_settle_ms,
        )

        self._pick_coord.request_pick(cfg=cfg, on_confirm=on_confirm)

    # ---------- 未保存变更守卫辅助 ----------

    def _guard_confirm_wrapper(self, action_name: str, ctx: ProfileContext) -> bool:
        g = getattr(self, "_guard", None)
        if g is None:
            return True
        return g.confirm(action_name, ctx)

    def _flush_all_pages(self) -> None:
        """
        将各页面的表单状态刷新到模型中（不保存到磁盘）。
        供 UnsavedChangesGuard 使用。
        """
        try:
            self._page_base.flush_to_model()
        except Exception:
            log.exception("MainWindow._flush_all_pages: base page flush_to_model failed")

        try:
            self._page_skills.flush_to_model()
        except Exception:
            log.exception("MainWindow._flush_all_pages: skills page flush_to_model failed")

        try:
            self._page_points.flush_to_model()
        except Exception:
            log.exception("MainWindow._flush_all_pages: points page flush_to_model failed")

        try:
            self._page_rotation.flush_to_model()
        except Exception:
            log.exception("MainWindow._flush_all_pages: rotation presets page flush_to_model failed")

        try:
            self._page_rotation_editor.flush_to_model()
        except Exception:
            log.exception("MainWindow._flush_all_pages: rotation editor page flush_to_model failed")

    def _set_pages_context(self, ctx: ProfileContext) -> None:
        """
        在 rollback 之后刷新页面绑定的 ctx 对象。
        """
        try:
            self._page_base.set_context(ctx)
        except Exception:
            log.exception("MainWindow._set_pages_context: set_context failed for base page")

        try:
            self._page_skills.set_context(ctx)
        except Exception:
            log.exception("MainWindow._set_pages_context: set_context failed for skills page")

        try:
            self._page_points.set_context(ctx)
        except Exception:
            log.exception("MainWindow._set_pages_context: set_context failed for points page")

        try:
            self._page_rotation.set_context(ctx)
        except Exception:
            log.exception("MainWindow._set_pages_context: set_context failed for rotation presets page")

        try:
            self._page_rotation_editor.set_context(ctx)
        except Exception:
            log.exception("MainWindow._set_pages_context: set_context failed for rotation editor page")

    # ---------- 从方案页打开循环编辑器 ----------

    def _open_rotation_editor(self, preset_id: str) -> None:
        """
        由 RotationPresetsPage 调用：
        - 定位到指定 preset
        - 切换中央 stack 到循环编辑器页
        - 左侧导航仍高亮“循环/轨道方案”
        """
        pid = (preset_id or "").strip()
        if not pid:
            return

        # 确保循环编辑器使用最新的 ProfileContext
        try:
            self._page_rotation_editor.set_context(self._ctx)
        except Exception:
            log.exception("set_context failed for RotationEditorPage in _open_rotation_editor")

        # 让编辑器选中并打开指定的 preset
        try:
            self._page_rotation_editor.open_preset(pid)
        except Exception:
            log.exception("open_preset failed in _open_rotation_editor")

        idx = self._page_indices.get("rotation_editor")
        if idx is not None:
            self._stack.setCurrentIndex(idx)
            try:
                # 左侧导航仍高亮“循环/轨道方案”这一项
                self._nav.set_active_page("rotation")
            except Exception:
                pass

            self.status.set_page("循环编辑器")
            self.status.status_msg("ready", ttl_ms=1000)

    # ---------- GW2 技能导入对话框 ----------

    # ---------- GW2 技能导入对话框 ----------

    def _open_gw2_skill_import_dialog(self) -> None:
        """
        打开 GW2 技能导入插件窗口。
        导入完成后会刷新技能配置页的列表。
        """
        try:
            dlg = Gw2SkillImportDialog(
                parent=self,
                ctx=self._ctx,
                services=self.services,
                on_imported=self._page_skills.refresh_tree,  # 导入后刷新列表
            )
            dlg.exec()
        except Exception as e:
            log.exception("failed to open Gw2SkillImportDialog")
            self.notify.error("无法打开 GW2 技能导入窗口", detail=str(e))
    # ---------- 关闭事件：先守卫未保存变更，再停止取色并保存几何 ----------

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        关闭事件：
        1) 先通过 UnsavedChangesGuard 检查未保存更改；
        2) 再关闭取色协调器、快捷执行面板和执行热键监听器；
        3) 最后持久化窗口几何到 app_state.json。
        """
        # 先检查未保存更改
        g = getattr(self, "_guard", None)
        if g is not None:
            try:
                ok = g.confirm("退出程序", self._ctx)
            except Exception:
                log.exception("UnsavedChangesGuard.confirm failed in MainWindow.closeEvent")
                ok = True  # 守卫报错时，默认允许关闭，避免卡死
            if not ok:
                event.ignore()
                return

        # 停止取色协调器
        try:
            self._pick_coord.close()
        except Exception:
            log.exception("failed to close QtPickCoordinator in MainWindow.closeEvent")

        # 关闭快捷执行面板（如果存在）
        try:
            if hasattr(self, "_quick_panel") and self._quick_panel is not None:
                self._quick_panel.close()
        except Exception:
            log.exception("failed to close QuickExecPanel in MainWindow.closeEvent")

        # 停止执行热键监听器
        try:
            if self._exec_hotkey is not None:
                self._exec_hotkey.close()
        except Exception:
            log.exception("failed to close ExecHotkeyController in MainWindow.closeEvent")

        # 保存当前窗口几何到 app_state.json
        try:
            self._win_state.persist_current_geometry()
        except Exception:
            log.exception("persist_current_geometry failed in MainWindow.closeEvent")

        event.accept()

    def _toggle_exec_by_hotkey(self) -> None:
        """
        由 ExecHotkeyController 触发：
        - 若循环引擎未运行，则启动当前 RotationEditorPage 选中的方案；
        - 若正在运行，则停止。
        在 Qt 主线程中执行（由 QtDispatcher 保证）。
        """
        try:
            page = self._page_rotation_editor
        except Exception:
            return
        if page is None:
            return

        try:
            page.toggle_engine_via_hotkey()
        except Exception as e:
            # 这里捕获所有异常，避免热键回调把 UI 弄崩；具体错误交给 UiNotify
            self.notify.error("执行启停热键失败", detail=str(e))

    def _on_quick_exec_requested(self) -> None:
        """
        打开/关闭快捷执行面板。
        """
        if self._quick_panel is None:
            try:
                # 同样使用 parent=None，保持独立顶层窗口特性
                self._quick_panel = QuickExecPanel(
                    ctx=self._ctx,
                    engine_host=self._page_rotation_editor,
                    open_editor_cb=self._open_rotation_editor,
                    parent=None,
                )
            except Exception:
                self.notify.error("无法创建快捷执行面板")
                return

        try:
            self._quick_panel.set_context(self._ctx)
        except Exception:
            pass

        if self._quick_panel.isVisible():
            self._quick_panel.hide()
        else:
            self._quick_panel.show()
            self._quick_panel.raise_()
            self._quick_panel.activateWindow()