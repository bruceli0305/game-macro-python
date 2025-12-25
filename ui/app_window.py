from __future__ import annotations

import tkinter as tk

import ttkbootstrap as tb
import logging

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.models.app_state import AppState
from core.profiles import ProfileContext, ProfileManager
from core.repos.app_state_repo import AppStateRepo

from core.app.services.app_services import AppServices
from core.app.services.profile_service import ProfileService
from core.app.pick_orchestrator import PickOrchestrator
from core.input.global_hotkeys import HotkeyConfig

from core.events.payloads import DirtyStateChangedPayload
# optional pick engine
try:
    from core.pick.pick_service import PickService, PickConfig
    from core.pick.capture import SampleSpec
except Exception:
    PickService = None  # type: ignore
    PickConfig = None  # type: ignore
    SampleSpec = None  # type: ignore

from ui.nav import NavFrame

from ui.app.event_pump import EventPump
from ui.app.pages_manager import PagesManager
from ui.app.pick_ui import PickUiController
from ui.app.profile_controller import ProfileController
from ui.app.status import StatusBar, StatusController
from ui.app.hotkeys_controller import HotkeysController
from ui.app.unsaved_guard import UnsavedChangesGuard
from ui.app.window_state import WindowStateController


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
        event_bus: EventBus,
        app_state_repo: AppStateRepo,
        app_state: AppState,
    ) -> None:
        super().__init__(themename=themename)

        self._pm = profile_manager
        self._ctx = profile_ctx
        self._bus = event_bus
        self._app_state_repo = app_state_repo
        self._app_state = app_state

        self._base_title = "Game Macro - Phase 1"
        self.title(self._base_title)

        # ---- services / orchestrators ----
        self._services = AppServices(bus=self._bus, ctx=self._ctx)
        self._profile_service = ProfileService(pm=self._pm, services=self._services, bus=self._bus)
        self._pick_orch = PickOrchestrator(bus=self._bus, services=self._services)

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

        # ---- controllers ----
        self._status = StatusController(root=self, bar=self._status_bar, bus=self._bus)

        # hotkeys controller: reload on HOTKEYS_CHANGED
        self._hotkeys = HotkeysController(
            bus=self._bus,
            config_provider=lambda: HotkeyConfig(
                enter_pick_mode=self._ctx.base.hotkeys.enter_pick_mode,
                cancel_pick=self._ctx.base.hotkeys.cancel_pick,
            ),
        )
        self._hotkeys.start()

        # pages
        self._pages = PagesManager(master=self._content, ctx=self._ctx, bus=self._bus, services=self._services)

        # pick ui controller (preview/avoidance only)
        self._pick_ui = PickUiController(root=self, bus=self._bus, ctx_provider=lambda: self._ctx)

        # unsaved guard (UoW-driven)
        self._guard = UnsavedChangesGuard(
            root=self,
            services=self._services,
            pages=self._pages,
            backup_provider=lambda: bool(self._ctx.base.io.backup_on_save),
        )

        # profile controller (dialogs + calling profile service)
        self._profile_ctrl = ProfileController(
            root=self,
            bus=self._bus,
            profile_service=self._profile_service,
            apply_ctx_to_ui=self._apply_ctx_to_ui,
            refresh_profiles_ui=self._refresh_profiles_ui,
            guard_confirm=lambda action_name: self._guard.confirm(action_name=action_name, ctx=self._ctx),
        )

        # ---- optional pick engine ----
        self._pick = None
        if PickService is not None and PickConfig is not None and SampleSpec is not None:
            self._pick = PickService(
                bus=self._bus,
                pick_config_provider=lambda: PickConfig(
                    delay_ms=int(self._ctx.base.pick.avoidance.delay_ms),
                    preview_throttle_ms=30,
                    error_throttle_ms=800,
                ),
                capture_spec_provider=self._capture_spec_for_context,
            )

        # ---- bus glue ----
        self._bus.subscribe(EventType.DIRTY_STATE_CHANGED, self._on_dirty_state_changed)

        # preview window click -> cancel pick
        self.bind("<<PICK_PREVIEW_CANCEL>>", lambda _e: self._bus.post_payload(EventType.PICK_CANCEL_REQUEST, None))

        # ---- event pump ----
        self._pump = EventPump(
            root=self,
            bus=self._bus,
            tick_ms=16,
            on_handler_error=lambda ev, e: self._status.set_status(
                f"ERROR: handler failed ({ev.type.value}): {e}", ttl_ms=5000
            ),
        )
        self._pump.start()

        # ---- initial UI state ----
        self._status.set_profile(self._ctx.profile_name)
        self._status.set_page("基础配置")
        self._pages.show("base")
        self._refresh_profiles_ui(self._ctx.profile_name)
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

    def _tk_exc_handler(exc, val, tb_):
        log = logging.getLogger("tk")
        log.exception("tk callback exception", exc_info=(exc, val, tb_))

    def _on_profile_action(self, action: str) -> None:
        self._profile_ctrl.on_action(action, self._ctx)

    # ---------- apply new ProfileContext ----------
    def _apply_ctx_to_ui(self, ctx: ProfileContext) -> None:
        """
        Called after ProfileService has already bound ctx into AppServices.
        """
        self._ctx = ctx

        # status bar
        self._status.set_profile(ctx.profile_name)

        # apply theme immediately (so user feels the switch)
        try:
            self.style.theme_use(ctx.base.ui.theme or "darkly")
        except Exception:
            pass

        # pages get new ctx
        self._pages.set_context(ctx)

        # hotkeys depend on ctx.base
        try:
            self._hotkeys.start()
        except Exception:
            pass

        # refresh profile combobox
        self._refresh_profiles_ui(ctx.profile_name)

        # notify dirty
        self._services.notify_dirty()

    def _refresh_profiles_ui(self, select: str) -> None:
        names = self._profile_service.list_profiles()
        self._nav.set_profiles(names, select)

    # ---------- pick capture spec mapping ----------
    def _capture_spec_for_context(self, ctx_ref) -> tuple["SampleSpec", str]:
        """
        Step 7:
        PickService.capture_spec_provider 入参改为 PickContextRef（不再使用 dict）。
        """
        mon = (self._ctx.base.capture.monitor_policy or "primary")
        mode = "single"
        radius = 0

        try:
            typ = getattr(ctx_ref, "type", None)
            oid = getattr(ctx_ref, "id", None)

            if typ == "skill_pixel" and isinstance(oid, str):
                for s in self._ctx.skills.skills:
                    if s.id == oid:
                        mode = (s.pixel.sample.mode or "single")
                        radius = int(getattr(s.pixel.sample, "radius", 0) or 0)
                        mon = (s.pixel.monitor or mon)
                        break

            elif typ == "point" and isinstance(oid, str):
                for p in self._ctx.points.points:
                    if p.id == oid:
                        mode = (p.sample.mode or "single")
                        radius = int(getattr(p.sample, "radius", 0) or 0)
                        mon = (p.monitor or mon)
                        break
        except Exception:
            pass

        return SampleSpec(mode=mode, radius=radius), mon
    # ---------- dirty title ----------
    def _on_dirty_state_changed(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, DirtyStateChangedPayload):
            return
        title = self._base_title + (" *" if p.dirty else "")
        try:
            if self.title() != title:
                self.title(title)
        except Exception:
            pass

    # ---------- close ----------
    def _on_close(self) -> None:
        if not self._guard.confirm(action_name="退出程序", ctx=self._ctx):
            return

        # cancel pick session
        self._bus.post_payload(EventType.PICK_CANCEL_REQUEST, None)

        # stop controllers/services
        try:
            self._pump.stop()
        except Exception:
            pass

        try:
            self._hotkeys.stop()
        except Exception:
            pass

        if self._pick is not None:
            try:
                self._pick.close()
            except Exception:
                pass

        try:
            self._pick_ui.close()
        except Exception:
            pass

        # persist window geometry
        self._win_state.persist_current_geometry()

        self.destroy()