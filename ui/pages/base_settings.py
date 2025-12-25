from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import messagebox

from core.event_bus import EventBus
from core.event_types import EventType
from core.models.common import clamp_int
from core.profiles import ProfileContext
from core.app.services.base_settings_service import BaseSettingsPatch
from ui.widgets.hotkey_entry import HotkeyEntry
from core.events.payloads import InfoPayload, ErrorPayload

from core.models.base import BaseFile

_DARK_THEMES = ["darkly", "superhero", "cyborg", "solar", "vapor"]
_LIGHT_THEMES = ["flatly", "litera", "cosmo", "journal", "minty", "lumen", "pulse", "sandstone", "simplex", "yeti"]

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


class BaseSettingsPage(tb.Frame):
    def __init__(self, master: tk.Misc, *, ctx: ProfileContext, bus: EventBus, services=None) -> None:
        super().__init__(master)
        self._ctx = ctx
        self._bus = bus
        self._services = services

        self._building = False
        self._dirty = False

        self.columnconfigure(0, weight=1)

        top = tb.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        tb.Label(top, text="基础配置", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        self._var_dirty = tk.StringVar(value="")
        tb.Label(top, textvariable=self._var_dirty, bootstyle=WARNING).grid(row=0, column=1, sticky="e")

        b = self._ctx.base

        self.var_theme = tk.StringVar(value=b.ui.theme or "darkly")
        self.var_monitor_policy_disp = tk.StringVar(value=_MONITOR_VAL_TO_DISP.get(b.capture.monitor_policy, "主屏"))

        self.var_hotkey_enter_pick = tk.StringVar(value=b.hotkeys.enter_pick_mode or "ctrl+alt+p")
        self.var_hotkey_cancel_pick = tk.StringVar(value=b.hotkeys.cancel_pick or "esc")

        av = b.pick.avoidance
        self.var_avoid_mode_disp = tk.StringVar(value=_AVOID_VAL_TO_DISP.get(av.mode, "隐藏主窗口"))
        self.var_avoid_delay = tk.IntVar(value=int(av.delay_ms))
        self.var_preview_follow = tk.BooleanVar(value=bool(av.preview_follow_cursor))
        self.var_preview_offset_x = tk.IntVar(value=int(av.preview_offset[0]))
        self.var_preview_offset_y = tk.IntVar(value=int(av.preview_offset[1]))
        self.var_preview_anchor_disp = tk.StringVar(value=_ANCHOR_VAL_TO_DISP.get(av.preview_anchor, "右下"))

        self.var_auto_save = tk.BooleanVar(value=bool(b.io.auto_save))
        self.var_backup = tk.BooleanVar(value=bool(b.io.backup_on_save))

        container = tb.Frame(self)
        container.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        self._build_ui_group(container)
        self._build_pick_group(container)
        self._build_io_group(container)

        btns = tb.Frame(self)
        btns.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        btns.columnconfigure(0, weight=1)

        tb.Button(btns, text="保存", bootstyle=SUCCESS, command=self._on_save).pack(side=RIGHT)
        tb.Button(btns, text="重新加载(放弃未保存)", command=self._on_reload).pack(side=RIGHT, padx=(0, 8))

        self._install_dirty_watchers()
        self._set_dirty(False)

    def is_dirty(self) -> bool:
        return bool(self._dirty)

    # --- standardized flush (no validation) ---
    def flush_to_model(self) -> None:
        if self._building:
            return
        if self._services is None:
            return

        patch = self._collect_patch()
        try:
            # apply without saving (may raise validation error; ignore here)
            self._services.base.apply_patch(patch)
        except Exception:
            # flush should not block leave-confirm; we keep model best-effort
            pass

    def _collect_patch(self) -> BaseSettingsPatch:
        theme = (self.var_theme.get() or "").strip()
        if theme == "---":
            theme = "darkly"

        return BaseSettingsPatch(
            theme=theme or "darkly",
            monitor_policy=_MONITOR_DISP_TO_VAL.get(self.var_monitor_policy_disp.get(), "primary"),

            hotkey_enter_pick=(self.var_hotkey_enter_pick.get() or "").strip(),
            hotkey_cancel_pick=(self.var_hotkey_cancel_pick.get() or "").strip(),

            avoid_mode=_AVOID_DISP_TO_VAL.get(self.var_avoid_mode_disp.get(), "hide_main"),
            avoid_delay_ms=clamp_int(int(self.var_avoid_delay.get()), 0, 5000),
            preview_follow=bool(self.var_preview_follow.get()),
            preview_offset_x=int(self.var_preview_offset_x.get()),
            preview_offset_y=int(self.var_preview_offset_y.get()),
            preview_anchor=_ANCHOR_DISP_TO_VAL.get(self.var_preview_anchor_disp.get(), "bottom_right"),

            auto_save=bool(self.var_auto_save.get()),
            backup_on_save=bool(self.var_backup.get()),
        )

    def _clear_hotkey_errors(self) -> None:
        try:
            if hasattr(self, "_hk_enter"):
                self._hk_enter.clear_error()
            if hasattr(self, "_hk_cancel"):
                self._hk_cancel.clear_error()
        except Exception:
            pass

    def _apply_hotkey_error(self, msg: str) -> None:
        """
        Parse service ValueError messages and highlight the correct field.
        """
        s = (msg or "").strip()
        self._clear_hotkey_errors()

        if s.startswith("enter_pick_mode:"):
            try:
                self._hk_enter.set_error(s.split(":", 1)[1].strip())
            except Exception:
                pass
            return

        if s.startswith("cancel_pick:"):
            try:
                self._hk_cancel.set_error(s.split(":", 1)[1].strip())
            except Exception:
                pass
            return

        if s.startswith("hotkeys:"):
            # conflict: highlight both
            detail = s.split(":", 1)[1].strip()
            try:
                self._hk_enter.set_error(detail)
                self._hk_cancel.set_error(detail)
            except Exception:
                pass

    def _validate_hotkeys_live(self) -> None:
        """
        Live validation (best-effort). Only runs when services injected.
        """
        if self._services is None:
            return
        try:
            patch = self._collect_patch()
            self._services.base.validate_patch(patch)
            self._clear_hotkey_errors()
        except Exception as e:
            self._apply_hotkey_error(str(e))
    # ---------------- dirty ----------------
    def _install_dirty_watchers(self) -> None:
        def on_any(*_args) -> None:
            if self._building:
                return
            self._set_dirty(True)
            self._validate_hotkeys_live()

        for v in [
            self.var_theme,
            self.var_monitor_policy_disp,
            self.var_hotkey_enter_pick,
            self.var_hotkey_cancel_pick,
            self.var_avoid_mode_disp,
            self.var_avoid_delay,
            self.var_preview_follow,
            self.var_preview_offset_x,
            self.var_preview_offset_y,
            self.var_preview_anchor_disp,
            self.var_auto_save,
            self.var_backup,
        ]:
            v.trace_add("write", on_any)

    def _set_dirty(self, flag: bool) -> None:
        self._dirty = bool(flag)
        self._var_dirty.set("未保存*" if self._dirty else "")

        if self._services is not None:
            try:
                if self._dirty:
                    self._services.uow.mark_dirty("base")
                else:
                    self._services.uow.clear_dirty("base")
                self._services.notify_dirty()
            except Exception:
                pass

    # ---------------- UI groups ----------------
    def _build_ui_group(self, master: tb.Frame) -> None:
        lf = tb.Labelframe(master, text="界面 / 截图 / 热键", padding=10)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        lf.columnconfigure(1, weight=1)

        tb.Label(lf, text="主题").grid(row=0, column=0, sticky="w", pady=4)
        themes = _DARK_THEMES + ["---"] + _LIGHT_THEMES
        tb.Combobox(lf, textvariable=self.var_theme, values=themes, state="readonly").grid(
            row=0, column=1, sticky="ew", pady=4
        )

        tb.Label(lf, text="截图屏幕策略").grid(row=1, column=0, sticky="w", pady=4)
        tb.Combobox(
            lf,
            textvariable=self.var_monitor_policy_disp,
            values=list(_MONITOR_DISP_TO_VAL.keys()),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=4)

        tb.Label(lf, text="热键：进入取色").grid(row=2, column=0, sticky="w", pady=4)
        self._hk_enter = HotkeyEntry(lf, textvariable=self.var_hotkey_enter_pick)
        self._hk_enter.grid(row=2, column=1, sticky="ew", pady=4)
        tb.Label(lf, text="热键：取消取色").grid(row=3, column=0, sticky="w", pady=4)
        self._hk_cancel = HotkeyEntry(lf, textvariable=self.var_hotkey_cancel_pick)
        self._hk_cancel.grid(row=3, column=1, sticky="ew", pady=4)
    def _build_pick_group(self, master: tb.Frame) -> None:
        lf = tb.Labelframe(master, text="取色避让", padding=10)
        lf.grid(row=0, column=1, sticky="nsew")
        lf.columnconfigure(1, weight=1)

        tb.Label(lf, text="避让模式").grid(row=0, column=0, sticky="w", pady=4)
        tb.Combobox(
            lf,
            textvariable=self.var_avoid_mode_disp,
            values=list(_AVOID_DISP_TO_VAL.keys()),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        tb.Label(lf, text="延迟(ms)").grid(row=1, column=0, sticky="w", pady=4)
        tb.Spinbox(lf, from_=0, to=5000, increment=10, textvariable=self.var_avoid_delay).grid(
            row=1, column=1, sticky="ew", pady=4
        )

        tb.Checkbutton(lf, text="预览跟随鼠标", variable=self.var_preview_follow).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 4)
        )

        tb.Label(lf, text="预览偏移 X").grid(row=3, column=0, sticky="w", pady=4)
        tb.Spinbox(lf, from_=-500, to=500, increment=1, textvariable=self.var_preview_offset_x).grid(
            row=3, column=1, sticky="ew", pady=4
        )

        tb.Label(lf, text="预览偏移 Y").grid(row=4, column=0, sticky="w", pady=4)
        tb.Spinbox(lf, from_=-500, to=500, increment=1, textvariable=self.var_preview_offset_y).grid(
            row=4, column=1, sticky="ew", pady=4
        )

        tb.Label(lf, text="预览锚点").grid(row=5, column=0, sticky="w", pady=4)
        tb.Combobox(
            lf,
            textvariable=self.var_preview_anchor_disp,
            values=list(_ANCHOR_DISP_TO_VAL.keys()),
            state="readonly",
        ).grid(row=5, column=1, sticky="ew", pady=4)

    def _build_io_group(self, master: tb.Frame) -> None:
        lf = tb.Labelframe(master, text="保存策略", padding=10)
        lf.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        lf.columnconfigure(0, weight=1)

        tb.Checkbutton(lf, text="自动保存（CRUD 时生效）", variable=self.var_auto_save).grid(
            row=0, column=0, sticky="w", pady=4
        )
        tb.Checkbutton(lf, text="保存时生成 .bak 备份", variable=self.var_backup).grid(
            row=1, column=0, sticky="w", pady=4
        )

    # ---------------- lifecycle ----------------
    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._building = True
        try:
            b = self._ctx.base
            self.var_theme.set(b.ui.theme or "darkly")
            self.var_monitor_policy_disp.set(_MONITOR_VAL_TO_DISP.get(b.capture.monitor_policy, "主屏"))
            self.var_hotkey_enter_pick.set(b.hotkeys.enter_pick_mode or "ctrl+alt+p")
            self.var_hotkey_cancel_pick.set(b.hotkeys.cancel_pick or "esc")

            av = b.pick.avoidance
            self.var_avoid_mode_disp.set(_AVOID_VAL_TO_DISP.get(av.mode, "隐藏主窗口"))
            self.var_avoid_delay.set(int(av.delay_ms))
            self.var_preview_follow.set(bool(av.preview_follow_cursor))
            self.var_preview_offset_x.set(int(av.preview_offset[0]))
            self.var_preview_offset_y.set(int(av.preview_offset[1]))
            self.var_preview_anchor_disp.set(_ANCHOR_VAL_TO_DISP.get(av.preview_anchor, "右下"))

            self.var_auto_save.set(bool(b.io.auto_save))
            self.var_backup.set(bool(b.io.backup_on_save))
        finally:
            self._building = False
        self._set_dirty(False)

    # ---------------- actions ----------------
    def _on_reload(self) -> None:
        if self._services is None:
            # fallback legacy behavior
            try:
                self._ctx.base = self._ctx.base_repo.load_or_create()
                self.set_context(self._ctx)
                self._bus.post_payload(EventType.INFO, InfoPayload(msg="已重新加载 base.json"))
            except Exception as e:
                self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"重新加载失败", detail=str(e)))
            return

        try:
            self._services.base.reload_cmd()
            self.set_context(self._services.ctx)
            self._set_dirty(False)
        except Exception as e:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"重新加载失败", detail=str(e)))

    def _on_save(self) -> None:
        patch = self._collect_patch()

        if self._services is None:
            messagebox.showerror("保存失败", "services 未注入", parent=self.winfo_toplevel())
            return

        try:
            self._services.base.save_cmd(patch)
            self._set_dirty(False)
        except Exception as e:
            self._apply_hotkey_error(str(e))
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"保存失败", detail=str(e)))
            messagebox.showerror("保存失败", f"{e}", parent=self.winfo_toplevel())
    def _apply_to_basefile(self, b: BaseFile, patch: BaseSettingsPatch) -> None:
        # theme
        theme = (patch.theme or "").strip()
        if theme == "---" or not theme:
            theme = "darkly"
        b.ui.theme = theme

        # capture
        b.capture.monitor_policy = (patch.monitor_policy or "primary").strip() or "primary"

        # hotkeys（已在 validate_patch 校验）
        b.hotkeys.enter_pick_mode = (patch.hotkey_enter_pick or "").strip()
        b.hotkeys.cancel_pick = (patch.hotkey_cancel_pick or "").strip()

        # avoidance
        av = b.pick.avoidance
        av.mode = (patch.avoid_mode or "hide_main").strip() or "hide_main"
        av.delay_ms = clamp_int(int(patch.avoid_delay_ms), 0, 5000)
        av.preview_follow_cursor = bool(patch.preview_follow)
        av.preview_offset = (int(patch.preview_offset_x), int(patch.preview_offset_y))
        av.preview_anchor = (patch.preview_anchor or "bottom_right").strip() or "bottom_right"

        # io
        b.io.auto_save = bool(patch.auto_save)
        b.io.backup_on_save = bool(patch.backup_on_save)