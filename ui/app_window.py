from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

import ttkbootstrap as tb
from ttkbootstrap.constants import LEFT, X, Y, VERTICAL

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.models.app_state import AppState
from core.profiles import ProfileContext, ProfileManager
from core.repos.app_state_repo import AppStateRepo
from core.app.services.app_services import AppServices
from core.app.pick_orchestrator import PickOrchestrator
from core.input.global_hotkeys import GlobalHotkeyService, HotkeyConfig

# Pick service is optional but present in your codebase
try:
    from core.pick.pick_service import PickService, PickConfig
    from core.pick.capture import SampleSpec
except Exception:
    PickService = None  # type: ignore
    PickConfig = None  # type: ignore
    SampleSpec = None  # type: ignore

from ui.nav import NavFrame
from ui.pages.base_settings import BaseSettingsPage
from ui.pages.skills import SkillsPage
from ui.pages.points import PointsPage
from ui.pick_preview_window import PickPreviewWindow

try:
    from ttkbootstrap.toast import ToastNotification  # type: ignore
except Exception:
    ToastNotification = None


class StatusBar(tb.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(10, 6))
        self._profile_var = tk.StringVar(value="profile: -")
        self._page_var = tk.StringVar(value="page: -")
        self._status_var = tk.StringVar(value="ready")

        tb.Label(self, textvariable=self._profile_var).pack(side=LEFT)
        tb.Separator(self, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)
        tb.Label(self, textvariable=self._page_var).pack(side=LEFT)
        tb.Separator(self, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)
        tb.Label(self, textvariable=self._status_var, anchor="w").pack(side=LEFT, fill=X, expand=True)

    def set_profile(self, name: str) -> None:
        self._profile_var.set(f"profile: {name}")

    def set_page(self, name: str) -> None:
        self._page_var.set(f"page: {name}")

    def set_status(self, text: str) -> None:
        self._status_var.set(text)


class AppWindow(tb.Window):
    """
    - Profile management
    - Global unsaved changes confirm
    - Pick UI closure:
        * subscribe PICK_* events
        * show PickPreviewWindow
        * apply avoidance (hide/minimize/move_aside/none) and restore
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

        self._status_after_id: str | None = None
        self._toast_available = ToastNotification is not None

        self._base_title = "Game Macro - Phase 1"
        self.title(self._base_title)
        # application services (UnitOfWork + domain services)
        self._services = AppServices(bus=self._bus, ctx=self._ctx)
        # application-level pick handler
        self._pick_orch = PickOrchestrator(bus=self._bus, services=self._services)
        # ---- pick ui state ----
        self._preview: PickPreviewWindow | None = None
        self._pick_active = False
        self._prev_geo: str | None = None
        self._prev_state: str | None = None
        self._avoid_mode_applied: str | None = None

        self._apply_initial_geometry()

        # Layout
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._nav = NavFrame(
            self,
            on_nav=self.show_page,
            on_profile_select=self._on_profile_select,
            on_profile_action=self._on_profile_action,
        )
        self._nav.grid(row=0, column=0, sticky="nsw")

        self._content = tb.Frame(self, padding=12)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.rowconfigure(0, weight=1)
        self._content.columnconfigure(0, weight=1)

        self._status = StatusBar(self)
        self._status.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._status.set_profile(self._ctx.profile_name)

        self._page_title: dict[str, str] = {
            "base": "基础配置",
            "skills": "技能配置",
            "points": "取色点位配置",
        }
        self._pages: dict[str, tb.Frame] = {}
        self._build_pages()

        self._refresh_profile_list(select=self._ctx.profile_name)

        # hotkeys
        self._hotkeys = GlobalHotkeyService(
            bus=self._bus,
            config_provider=lambda: HotkeyConfig(
                enter_pick_mode=self._ctx.base.hotkeys.enter_pick_mode,
                cancel_pick=self._ctx.base.hotkeys.cancel_pick,
            ),
        )
        self._hotkeys.start()

        # pick service (optional)
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

        # ---- EventBus ----
        self._bus.subscribe(EventType.UI_THEME_CHANGE, self._on_theme_change)
        self._bus.subscribe(EventType.HOTKEYS_CHANGED, lambda _ev: self._hotkeys.start())
        self._bus.subscribe(EventType.INFO, self._on_info)
        self._bus.subscribe(EventType.ERROR, self._on_error)
        self._bus.subscribe(EventType.STATUS, self._on_status)
        self._bus.subscribe(EventType.DIRTY_STATE_CHANGED, self._on_dirty_state_changed)

        # pick ui subscriptions
        self._bus.subscribe(EventType.PICK_MODE_ENTERED, self._on_pick_mode_entered)
        self._bus.subscribe(EventType.PICK_PREVIEW, self._on_pick_preview)
        self._bus.subscribe(EventType.PICK_MODE_EXITED, self._on_pick_mode_exited)
        self._bus.subscribe(EventType.PICK_CANCELED, self._on_pick_canceled)
        self._bus.subscribe(EventType.PICK_CONFIRMED, self._on_pick_confirmed)

        self._services.notify_dirty()
        # preview window click cancel -> bus cancel
        self.bind("<<PICK_PREVIEW_CANCEL>>", lambda _e: self._bus.post(EventType.PICK_CANCEL_REQUEST))

        self.after(16, self._pump_events)

        self.show_page("base")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initial dirty indicator
        self._update_global_dirty_indicator()

    # ---------- pick sample mapping ----------
    def _capture_spec_for_context(self, ctx: dict) -> tuple["SampleSpec", str]:
        # default: use base monitor policy
        mon = (self._ctx.base.capture.monitor_policy or "primary")
        mode = "single"
        radius = 0

        try:
            typ = ctx.get("type")
            oid = ctx.get("id")

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

    # ---------------- Pages ----------------
    def _build_pages(self) -> None:
        self._pages["base"] = BaseSettingsPage(self._content, ctx=self._ctx, bus=self._bus, services=self._services)
        self._pages["skills"] = SkillsPage(self._content, ctx=self._ctx, bus=self._bus, services=self._services)
        self._pages["points"] = PointsPage(self._content, ctx=self._ctx, bus=self._bus, services=self._services)
        for p in self._pages.values():
            p.grid(row=0, column=0, sticky="nsew")

    def show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            self.set_status(f"ERROR: unknown page: {key}", ttl_ms=4000)
            return
        page.tkraise()
        self._status.set_page(self._page_title.get(key, key))
        self.set_status("ready")

    # ---------------- Profile switching ----------------
    def _refresh_profile_list(self, *, select: str | None = None) -> None:
        names = self._pm.list_profiles()
        if not names:
            names = ["Default"]
        current = select or self._ctx.profile_name
        self._nav.set_profiles(names, current)

    def _on_profile_select(self, name: str) -> None:
        if not self._confirm_leave_context(action_name="切换 Profile"):
            self._refresh_profile_list(select=self._ctx.profile_name)
            return
        # cancel pick if active to avoid weird state
        self._bus.post(EventType.PICK_CANCEL_REQUEST)
        self._switch_profile(name)

    def _on_profile_action(self, action: str) -> None:
        if action in ("new", "copy", "rename", "delete"):
            if not self._confirm_leave_context(action_name="Profile 操作"):
                self._refresh_profile_list(select=self._ctx.profile_name)
                return

        cur = self._ctx.profile_name

        if action == "new":
            name = simpledialog.askstring("新建 Profile", "请输入 Profile 名称：", parent=self)
            if not name:
                return
            try:
                ctx = self._pm.create_profile(name)
                self._switch_profile(ctx.profile_name)
            except Exception as e:
                self._bus.post(EventType.ERROR, msg=f"新建失败: {e}")
            return

        if action == "copy":
            name = simpledialog.askstring("复制 Profile", f"复制 {cur} 到新名称：", parent=self)
            if not name:
                return
            try:
                ctx = self._pm.copy_profile(cur, name)
                self._switch_profile(ctx.profile_name)
            except Exception as e:
                self._bus.post(EventType.ERROR, msg=f"复制失败: {e}")
            return

        if action == "rename":
            name = simpledialog.askstring("重命名 Profile", f"{cur} 重命名为：", parent=self)
            if not name:
                return
            try:
                ctx = self._pm.rename_profile(cur, name)
                self._switch_profile(ctx.profile_name)
            except Exception as e:
                self._bus.post(EventType.ERROR, msg=f"重命名失败: {e}")
            return

        if action == "delete":
            if cur == "Default":
                messagebox.showinfo("提示", "不建议删除 Default（可重命名/另建）。", parent=self)
                return
            ok = messagebox.askyesno("删除 Profile", f"确认删除 profile：{cur} ？\n\n（将删除该目录下所有 JSON）", parent=self)
            if not ok:
                return
            try:
                self._pm.delete_profile(cur)
                self._ctx = self._pm.current or self._pm.open_last_or_fallback()
                self._status.set_profile(self._ctx.profile_name)
                self._services.set_context(self._ctx)
                for key, page in self._pages.items():
                    if hasattr(page, "set_context"):
                        try:
                            page.set_context(self._ctx)  # type: ignore[attr-defined]
                        except Exception as e:
                            self._bus.post(EventType.ERROR, msg=f"页面刷新失败({key}): {e}")

                self._hotkeys.start()
                self._refresh_profile_list(select=self._ctx.profile_name)
                self._bus.post(EventType.INFO, msg=f"已删除 profile 并切换到 {self._ctx.profile_name}")
                self._update_global_dirty_indicator()
            except Exception as e:
                self._bus.post(EventType.ERROR, msg=f"删除失败: {e}")
            return

    def _switch_profile(self, name: str) -> None:
        if name == self._ctx.profile_name:
            return
        try:
            new_ctx = self._pm.open_profile(name)
        except Exception as e:
            self._bus.post(EventType.ERROR, msg=f"打开 profile 失败: {e}")
            self._refresh_profile_list(select=self._ctx.profile_name)
            return

        self._ctx = new_ctx
        self._status.set_profile(self._ctx.profile_name)
        self._services.set_context(self._ctx)
        try:
            self.style.theme_use(self._ctx.base.ui.theme or "darkly")
        except Exception:
            pass

        for key, page in self._pages.items():
            if hasattr(page, "set_context"):
                try:
                    page.set_context(self._ctx)  # type: ignore[attr-defined]
                except Exception as e:
                    self._bus.post(EventType.ERROR, msg=f"页面刷新失败({key}): {e}")

        self._hotkeys.start()
        self._refresh_profile_list(select=self._ctx.profile_name)
        self._bus.post(EventType.INFO, msg=f"已切换 profile: {self._ctx.profile_name}")
        self._update_global_dirty_indicator()

    # ---------------- Pick UI closure ----------------

    def _ensure_preview(self) -> None:
        if self._preview is None:
            try:
                self._preview = PickPreviewWindow(self)
            except Exception:
                self._preview = None

    def _apply_avoidance_on_enter(self) -> None:
        av = self._ctx.base.pick.avoidance
        mode = av.mode
        self._avoid_mode_applied = mode

        # store state
        try:
            self._prev_geo = self.geometry()
        except Exception:
            self._prev_geo = None
        try:
            self._prev_state = self.state()
        except Exception:
            self._prev_state = None

        if mode == "hide_main":
            try:
                self.withdraw()
            except Exception:
                pass
        elif mode == "minimize":
            try:
                self.iconify()
            except Exception:
                pass
        elif mode == "move_aside":
            # move to top-right of primary screen
            try:
                self.update_idletasks()
                sw = int(self.winfo_screenwidth())
                w = int(self.winfo_width())
                self.geometry(f"+{max(0, sw - w - 10)}+10")
            except Exception:
                pass
        # "none" -> do nothing

    def _restore_after_exit(self) -> None:
        mode = self._avoid_mode_applied
        self._avoid_mode_applied = None

        # restore window state
        try:
            if mode in ("hide_main", "minimize"):
                self.deiconify()
        except Exception:
            pass

        # restore geometry/state if we have them
        if self._prev_geo:
            try:
                self.geometry(self._prev_geo)
            except Exception:
                pass

        if self._prev_state:
            try:
                # state can be "normal"/"zoomed"/"iconic"/"withdrawn"
                if self._prev_state in ("normal", "zoomed"):
                    self.state(self._prev_state)
            except Exception:
                pass

        # bring to front (best-effort)
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _on_pick_mode_entered(self, _ev: Event) -> None:
        self._pick_active = True
        self._apply_avoidance_on_enter()
        self._ensure_preview()
        if self._preview is not None:
            try:
                self._preview.hide()
            except Exception:
                pass
        self._bus.post(EventType.STATUS, msg="取色模式已进入")

    def _on_pick_preview(self, ev: Event) -> None:
        # status text (still use sampled x/y)
        try:
            x = int(ev.payload.get("x", 0))
            y = int(ev.payload.get("y", 0))
            r = int(ev.payload.get("r", 0))
            g = int(ev.payload.get("g", 0))
            b = int(ev.payload.get("b", 0))
            hx = str(ev.payload.get("hex", ""))
        except Exception:
            return

        if hx:
            mon = ev.payload.get("monitor", "")
            abs_x = ev.payload.get("abs_x", None)
            abs_y = ev.payload.get("abs_y", None)

            if isinstance(abs_x, int) and isinstance(abs_y, int) and isinstance(mon, str) and mon:
                self.set_status(f"{mon} rel=({x},{y}) abs=({abs_x},{abs_y}) {hx}", ttl_ms=1200)
            elif isinstance(mon, str) and mon:
                self.set_status(f"{mon} rel=({x},{y}) {hx}", ttl_ms=1200)
            else:
                self.set_status(f"rel=({x},{y}) {hx}", ttl_ms=1200)
        else:
            self.set_status(f"x={x} y={y}", ttl_ms=1200)

        self._ensure_preview()
        if self._preview is None:
            return

        av = self._ctx.base.pick.avoidance

        # update content
        try:
            self._preview.update_preview(x=x, y=y, r=r, g=g, b=b)
        except Exception:
            pass

        # show (and lift) every time to avoid being hidden behind
        try:
            self._preview.show()
        except Exception:
            pass

        # Use Tk pointer coords for positioning (DPI-safe for tkinter window placement)
        try:
            px = int(self.winfo_pointerx())
            py = int(self.winfo_pointery())
        except Exception:
            px, py = x, y

        # Compute desired position
        try:
            ox, oy = int(av.preview_offset[0]), int(av.preview_offset[1])
        except Exception:
            ox, oy = 30, 30

        # Preview window size
        try:
            pw, ph = self._preview.size
        except Exception:
            pw, ph = (180, 74)

        if not av.preview_follow_cursor:
            nx, ny = 20, 20
        else:
            anchor = av.preview_anchor
            if anchor == "bottom_right":
                nx, ny = px + ox, py + oy
            elif anchor == "bottom_left":
                nx, ny = px - ox - pw, py + oy
            elif anchor == "top_right":
                nx, ny = px + ox, py - oy - ph
            elif anchor == "top_left":
                nx, ny = px - ox - pw, py - oy - ph
            else:
                nx, ny = px + ox, py + oy

        # Clamp to virtual screen bounds so it can't disappear off-screen
        L, T, R, B = self._get_virtual_screen_bounds()
        nx = self._clamp(int(nx), L, R - pw)
        ny = self._clamp(int(ny), T, B - ph)

        try:
            self._preview.move_to(nx, ny)
        except Exception:
            # fallback: safe fixed position
            try:
                self._preview.move_to(20, 20)
            except Exception:
                pass

    def _on_pick_confirmed(self, ev: Event) -> None:
        hx = ev.payload.get("hex", "")
        if isinstance(hx, str) and hx:
            self._bus.post(EventType.INFO, msg=f"取色确认: {hx}")

    def _on_pick_canceled(self, _ev: Event) -> None:
        self._bus.post(EventType.INFO, msg="取色已取消")

    def _on_pick_mode_exited(self, _ev: Event) -> None:
        self._pick_active = False

        # close preview
        if self._preview is not None:
            try:
                self._preview.destroy()
            except Exception:
                pass
            self._preview = None

        self._restore_after_exit()
        self._bus.post(EventType.STATUS, msg="取色模式已退出")

    def _get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """
        Return (L, T, R, B) bounds in screen coordinates.
        On Windows, use virtual screen metrics to support multi-monitor (including negative coords).
        Fallback to Tk screen size.
        """
        try:
            import ctypes
            user32 = ctypes.windll.user32
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79
            l = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
            t = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
            w = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
            h = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
            return l, t, l + w, t + h
        except Exception:
            # fallback: primary screen only
            return 0, 0, int(self.winfo_screenwidth()), int(self.winfo_screenheight())

    @staticmethod
    def _clamp(v: int, lo: int, hi: int) -> int:
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    # ---------------- Global dirty handling ----------------

    def _iter_pages(self):
        for k, p in self._pages.items():
            yield k, p

    def _page_is_dirty(self, page: tb.Frame) -> bool:
        if hasattr(page, "is_dirty"):
            try:
                return bool(page.is_dirty())  # type: ignore[attr-defined]
            except Exception:
                pass
        for attr in ("_dirty_disk", "_dirty"):
            if hasattr(page, attr):
                try:
                    return bool(getattr(page, attr))
                except Exception:
                    pass
        return False

    def _dirty_pages(self) -> list[str]:
        names: list[str] = []
        for key, page in self._iter_pages():
            if self._page_is_dirty(page):
                names.append(self._page_title.get(key, key))
        return names

    def _save_page(self, page: tb.Frame) -> bool:
        if hasattr(page, "save_changes"):
            try:
                return bool(page.save_changes())  # type: ignore[attr-defined]
            except Exception:
                return False
        if hasattr(page, "_on_save"):
            try:
                page._on_save()  # type: ignore[attr-defined]
                return not self._page_is_dirty(page)
            except Exception:
                return False
        return True

    def _save_all_dirty(self) -> bool:
        ok = True
        for _key, page in self._iter_pages():
            if self._page_is_dirty(page):
                if not self._save_page(page):
                    ok = False
        self._update_global_dirty_indicator()
        return ok

    def _confirm_leave_context(self, *, action_name: str) -> bool:
        dirty = self._dirty_pages()
        if not dirty:
            return True

        msg = (
            f"{action_name} 前检测到未保存更改：\n"
            + "\n".join([f" - {x}" for x in dirty])
            + "\n\n选择：\n"
              "【是】保存后继续\n"
              "【否】不保存继续\n"
              "【取消】返回"
        )
        res = messagebox.askyesnocancel("未保存更改", msg, parent=self)

        if res is None:
            return False
        if res is False:
            return True
        if not self._save_all_dirty():
            messagebox.showerror("保存失败", "部分页面保存失败，已取消操作。", parent=self)
            return False
        return True

    def _update_global_dirty_indicator(self) -> None:
        dirty = bool(self._dirty_pages())
        title = self._base_title + (" *" if dirty else "")
        try:
            if self.title() != title:
                self.title(title)
        except Exception:
            pass

    # ---------------- Status / Toast ----------------

    def set_status(self, text: str, *, ttl_ms: int | None = None) -> None:
        self._status.set_status(text)
        if self._status_after_id is not None:
            try:
                self.after_cancel(self._status_after_id)
            except Exception:
                pass
            self._status_after_id = None
        if ttl_ms is not None and ttl_ms > 0:
            self._status_after_id = self.after(ttl_ms, lambda: self._status.set_status("ready"))

    def _toast(self, title: str, message: str, bootstyle: str) -> None:
        if not self._toast_available:
            return
        try:
            ToastNotification(  # type: ignore[misc]
                title=title,
                message=message,
                duration=2500,
                bootstyle=bootstyle,
            ).show_toast()
        except Exception:
            pass

    # ---------------- EventBus ----------------

    def _pump_events(self) -> None:
        self._bus.dispatch_pending(
            max_events=200,
            on_error=lambda ev, e: self.set_status(f"ERROR: handler failed ({ev.type.value}): {e}", ttl_ms=5000),
        )
        # self._update_global_dirty_indicator()
        self.after(16, self._pump_events)

    def _on_theme_change(self, ev: Event) -> None:
        theme = ev.payload.get("theme")
        if isinstance(theme, str) and theme:
            try:
                self.style.theme_use(theme)
                self.set_status(f"INFO: theme -> {theme}", ttl_ms=2500)
            except Exception as e:
                self.set_status(f"ERROR: theme apply failed: {e}", ttl_ms=6000)
                self._toast("ERROR", f"theme apply failed: {e}", "danger")

    def _on_info(self, ev: Event) -> None:
        msg = ev.payload.get("msg", "")
        if isinstance(msg, str) and msg:
            self.set_status(f"INFO: {msg}", ttl_ms=3000)
            self._toast("INFO", msg, "success")

    def _on_error(self, ev: Event) -> None:
        msg = ev.payload.get("msg", "")
        if isinstance(msg, str) and msg:
            self.set_status(f"ERROR: {msg}", ttl_ms=6000)
            self._toast("ERROR", msg, "danger")

    def _on_status(self, ev: Event) -> None:
        msg = ev.payload.get("msg", "")
        if isinstance(msg, str) and msg:
            self.set_status(msg, ttl_ms=2000)

    # ---------------- Window persist ----------------

    def _apply_initial_geometry(self) -> None:
        w = int(getattr(self._app_state.window, "width", 1100) or 1100)
        h = int(getattr(self._app_state.window, "height", 720) or 720)
        x = getattr(self._app_state.window, "x", None)
        y = getattr(self._app_state.window, "y", None)
        if isinstance(x, int) and isinstance(y, int):
            self.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self.geometry(f"{w}x{h}")

    def _on_close(self) -> None:
        if not self._confirm_leave_context(action_name="退出程序"):
            return

        # cancel pick session
        self._bus.post(EventType.PICK_CANCEL_REQUEST)

        try:
            self._hotkeys.stop()
        except Exception:
            pass

        if self._pick is not None:
            try:
                self._pick.close()
            except Exception:
                pass

        # destroy preview if any
        if self._preview is not None:
            try:
                self._preview.destroy()
            except Exception:
                pass
            self._preview = None

        try:
            self.update_idletasks()
            self._app_state.window.width = int(self.winfo_width())
            self._app_state.window.height = int(self.winfo_height())
            self._app_state.window.x = int(self.winfo_x())
            self._app_state.window.y = int(self.winfo_y())
            self._app_state_repo.save(self._app_state)
        except Exception:
            pass

        self.destroy()
    def _on_dirty_state_changed(self, ev: Event) -> None:
        dirty = bool(ev.payload.get("dirty", False))
        title = self._base_title + (" *" if dirty else "")
        try:
            if self.title() != title:
                self.title(title)
        except Exception:
            pass