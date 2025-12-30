# File: ui/app_window.py
from __future__ import annotations

import logging
import tkinter as tk

import ttkbootstrap as tb

from core.models.app_state import AppState
from core.profiles import ProfileContext, ProfileManager
from core.repos.app_state_repo import AppStateRepo

from core.app.services.app_services import AppServices
from core.app.services.profile_service import ProfileService

from ui.nav import NavFrame
from ui.app.pages_manager import PagesManager
from ui.app.profile_controller import ProfileController
from ui.app.status import StatusBar, StatusController
from ui.app.unsaved_guard import UnsavedChangesGuard
from ui.app.window_state import WindowStateController
from ui.app.pick_coordinator import PickCoordinator, _UiPolicySnapshot
from ui.runtime.ui_dispatcher import UiDispatcher
from ui.app.notify import UiNotify

from core.pick.models import PickSessionConfig, PickConfirmed
from core.pick.capture import SampleSpec


class AppWindow(tb.Window):
    """
    Thin shell window:
    - assemble controllers and pages
    - minimal glue code only
    """

    def __init__(
        self,
        *,
        themename: str,
        profile_manager: ProfileManager,
        profile_ctx: ProfileContext,
        app_state_repo: AppStateRepo,
        app_state: AppState,
    ) -> None:
        super().__init__(themename=themename)

        self._pm = profile_manager
        self._ctx = profile_ctx
        self._app_state_repo = app_state_repo
        self._app_state = app_state

        # ---- UI dispatcher MUST exist before any UiNotify usage ----
        self._dispatcher = UiDispatcher(root=self, tick_ms=8, max_tasks_per_tick=400)
        self._dispatcher.start()

        self._base_title = "Game Macro - Phase 1"
        self.title(self._base_title)

        # ---- window state ----
        self._win_state = WindowStateController(root=self, repo=self._app_state_repo, state=self._app_state)
        self._win_state.apply_initial_geometry()

        # ---- layout ----
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._nav = NavFrame(
            self,
            on_nav=self._on_nav,
            on_profile_select=self._on_profile_select,
            on_profile_action=self._on_profile_action,
        )
        self._nav.grid(row=0, column=0, sticky="nsw")

        self._content = tb.Frame(self, padding=12)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.rowconfigure(0, weight=1)
        self._content.columnconfigure(0, weight=1)

        self._status_bar = StatusBar(self)
        self._status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

        # ---- controllers (Status first) ----
        self._status = StatusController(root=self, bar=self._status_bar)

        # ---- UiNotify (requires dispatcher + status) ----
        self._notify = UiNotify(call_soon=self._dispatcher.call_soon, status=self._status)

        # ---- services ----
        self._services = AppServices(
            ctx=self._ctx,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )
        self._profile_service = ProfileService(pm=self._pm, services=self._services)

        # pages（包含 Base/Skills/Points）
        self._pages = PagesManager(
            master=self._content,
            ctx=self._ctx,
            services=self._services,
            notify=self._notify,
            start_pick=self._start_pick_for_record,
        )

        # unsaved guard
        self._guard = UnsavedChangesGuard(
            root=self,
            services=self._services,
            pages=self._pages,
            backup_provider=lambda: bool(self._ctx.base.io.backup_on_save),
        )

        # profile controller (dialogs + calling profile service)
        self._profile_ctrl = ProfileController(
            root=self,
            profile_service=self._profile_service,
            apply_ctx_to_ui=self._apply_ctx_to_ui,
            refresh_profiles_ui=self._refresh_profiles_ui,
            guard_confirm=lambda action_name: self._guard.confirm(action_name=action_name, ctx=self._ctx),
            cancel_pick_sync=self._cancel_pick_sync,
            notify=self._notify,
        )

        # ---- pick coordinator (no EventBus) ----
        self._pick_coord = PickCoordinator(
            root=self,
            dispatcher=self._dispatcher,
            status=self._status,
            ui_policy_provider=self._ui_policy_snapshot,
        )

        # ---- 脏状态标题星号：直接订阅 AppStore ----
        try:
            self._services.store.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

        # ---- initial UI state ----
        self._status.set_profile(self._ctx.profile_name)
        self._status.set_page("基础配置")
        self._pages.show("base")
        self._refresh_profiles_ui(self._ctx.profile_name)
        # 主动广播一次当前 dirty 状态（即便通常为 clean）
        self._services.notify_dirty()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._tk_exc_handler

    # ---------- callbacks from Nav ----------
    def _on_nav(self, page_key: str) -> None:
        if not self._pages.show(page_key):
            self._status.set_status(f"ERROR: unknown page: {page_key}", ttl_ms=4000)
            return
        title = {"base": "基础配置", "skills": "技能配置", "points": "取色点位配置"}.get(page_key, page_key)
        self._status.set_page(title)
        self._status.set_status("ready", ttl_ms=800)

    def _on_profile_select(self, name: str) -> None:
        self._profile_ctrl.on_select(name, self._ctx)

    def _tk_exc_handler(self, exc, val, tb_):
        log = logging.getLogger("tk")
        log.exception("tk callback exception", exc_info=(exc, val, tb_))

    def _on_profile_action(self, action: str) -> None:
        self._profile_ctrl.on_action(action, self._ctx)

    # ---------- apply new ProfileContext ----------
    def _apply_ctx_to_ui(self, ctx: ProfileContext) -> None:
        self._ctx = ctx

        self._status.set_profile(ctx.profile_name)

        # apply theme immediately
        try:
            self.style.theme_use(ctx.base.ui.theme or "darkly")
        except Exception:
            pass

        self._pages.set_context(ctx)
        self._refresh_profiles_ui(ctx.profile_name)
        self._services.notify_dirty()

    def _refresh_profiles_ui(self, select: str) -> None:
        names = self._profile_service.list_profiles()
        self._nav.set_profiles(names, select)

    # ---------- pick: UI policy snapshot ----------
    def _ui_policy_snapshot(self) -> _UiPolicySnapshot:
        """
        从当前 ProfileContext 抽取取色相关的 UI 避让/预览策略快照。
        """
        b = self._ctx.base
        av = getattr(getattr(b, "pick", None), "avoidance", None)

        # 默认值
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

        return _UiPolicySnapshot(
            avoid_mode=mode or "hide_main",
            preview_follow=bool(preview_follow),
            preview_offset=preview_offset,
            preview_anchor=preview_anchor or "bottom_right",
        )

    # ---------- pick: pages -> coordinator ----------
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
            record_type=record_type,       # "skill_pixel" | "point"
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

    # ---------- dirty title ----------
    def _on_store_dirty(self, parts) -> None:
        try:
            dirty = bool(parts)
        except Exception:
            dirty = False
        title = self._base_title + (" *" if dirty else "")
        try:
            if self.title() != title:
                self.title(title)
        except Exception:
            pass

    # ---------- close ----------
    def _on_close(self) -> None:
        if not self._guard.confirm(action_name="退出程序", ctx=self._ctx):
            return

        # synchronous cancel pick (avoid race)
        self._cancel_pick_sync()

        try:
            self._pick_coord.close()
        except Exception:
            pass

        try:
            self._win_state.persist_current_geometry()
        except Exception:
            pass

        try:
            self._dispatcher.stop()
        except Exception:
            pass

        self.destroy()

    def _cancel_pick_sync(self) -> None:
        try:
            self._pick_coord.cancel()
        except Exception:
            pass