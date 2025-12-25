# File: ui/pages/base_settings.py
from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import messagebox

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.models.common import clamp_int
from core.profiles import ProfileContext
from core.app.services.base_settings_service import BaseSettingsPatch
from core.events.payloads import InfoPayload, ErrorPayload, DirtyStateChangedPayload

from ui.widgets.hotkey_entry import HotkeyEntry


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
    """
    Step 5:
    - 移除“全局进入取色/取消取色”热键（无用）
    - 新增：确认取色热键（PickService 使用）
    - 新增：鼠标避让配置（解决 hover 高亮污染像素）
    - dirty 展示只跟随 UoW（DIRTY_STATE_CHANGED）
    - 变更时 debounce 调 service.apply_patch，让 service 标记 dirty
    """

    def __init__(self, master: tk.Misc, *, ctx: ProfileContext, bus: EventBus, services) -> None:
        super().__init__(master)
        if services is None:
            raise RuntimeError("BaseSettingsPage requires services (cannot be None)")

        self._ctx = ctx
        self._bus = bus
        self._services = services

        self._building = False

        # dirty UI state (VIEW ONLY)
        self._dirty_ui = False

        # debounce apply
        self._apply_after_id: str | None = None

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

        # Step 5: confirm hotkey (Esc fixed cancel)
        self.var_pick_confirm_hotkey = tk.StringVar(value=getattr(b.pick, "confirm_hotkey", "") or "f8")

        av = b.pick.avoidance
        self.var_avoid_mode_disp = tk.StringVar(value=_AVOID_VAL_TO_DISP.get(av.mode, "隐藏主窗口"))
        self.var_avoid_delay = tk.IntVar(value=int(av.delay_ms))
        self.var_preview_follow = tk.BooleanVar(value=bool(av.preview_follow_cursor))
        self.var_preview_offset_x = tk.IntVar(value=int(av.preview_offset[0]))
        self.var_preview_offset_y = tk.IntVar(value=int(av.preview_offset[1]))
        self.var_preview_anchor_disp = tk.StringVar(value=_ANCHOR_VAL_TO_DISP.get(av.preview_anchor, "右下"))

        # Step 5: mouse avoidance
        self.var_mouse_avoid = tk.BooleanVar(value=bool(getattr(b.pick, "mouse_avoid", True)))
        self.var_mouse_avoid_offset_y = tk.IntVar(value=int(getattr(b.pick, "mouse_avoid_offset_y", 80)))
        self.var_mouse_avoid_settle_ms = tk.IntVar(value=int(getattr(b.pick, "mouse_avoid_settle_ms", 80)))

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

        # dirty UI 来自 UoW
        self._bus.subscribe(EventType.DIRTY_STATE_CHANGED, self._on_dirty_state_changed)
        self._set_dirty_ui(False)

    def _set_dirty_ui(self, flag: bool) -> None:
        self._dirty_ui = bool(flag)
        self._var_dirty.set("未保存*" if self._dirty_ui else "")

    def is_dirty(self) -> bool:
        return bool(self._dirty_ui)

    def _on_dirty_state_changed(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, DirtyStateChangedPayload):
            return
        parts = set(p.parts or [])
        self._set_dirty_ui("base" in parts)

    # --- standardized flush (best-effort) ---
    def flush_to_model(self) -> None:
        if self._building:
            return
        try:
            self._apply_now()
        except Exception:
            pass

    def _collect_patch(self) -> BaseSettingsPatch:
        theme = (self.var_theme.get() or "").strip()
        if theme == "---":
            theme = "darkly"

        return BaseSettingsPatch(
            theme=theme or "darkly",
            monitor_policy=_MONITOR_DISP_TO_VAL.get(self.var_monitor_policy_disp.get(), "primary"),

            pick_confirm_hotkey=(self.var_pick_confirm_hotkey.get() or "").strip(),

            avoid_mode=_AVOID_DISP_TO_VAL.get(self.var_avoid_mode_disp.get(), "hide_main"),
            avoid_delay_ms=clamp_int(int(self.var_avoid_delay.get()), 0, 5000),
            preview_follow=bool(self.var_preview_follow.get()),
            preview_offset_x=int(self.var_preview_offset_x.get()),
            preview_offset_y=int(self.var_preview_offset_y.get()),
            preview_anchor=_ANCHOR_DISP_TO_VAL.get(self.var_preview_anchor_disp.get(), "bottom_right"),

            mouse_avoid=bool(self.var_mouse_avoid.get()),
            mouse_avoid_offset_y=clamp_int(int(self.var_mouse_avoid_offset_y.get()), 0, 500),
            mouse_avoid_settle_ms=clamp_int(int(self.var_mouse_avoid_settle_ms.get()), 0, 500),

            auto_save=bool(self.var_auto_save.get()),
            backup_on_save=bool(self.var_backup.get()),
        )

    def _clear_hotkey_errors(self) -> None:
        try:
            if hasattr(self, "_hk_confirm"):
                self._hk_confirm.clear_error()
        except Exception:
            pass

    def _apply_hotkey_error(self, msg: str) -> None:
        """
        BaseSettingsService.validate_patch 会抛出 'confirm_hotkey: xxx' 格式错误。
        这里把错误展示到确认热键输入框上。
        """
        s = (msg or "").strip()
        self._clear_hotkey_errors()

        if "confirm_hotkey:" in s:
            try:
                self._hk_confirm.set_error(s.split(":", 1)[1].strip())
            except Exception:
                pass
            return

        # fallback: still show in confirm field
        try:
            self._hk_confirm.set_error(s)
        except Exception:
            pass

    def _validate_confirm_hotkey_live(self) -> None:
        try:
            patch = self._collect_patch()
            self._services.base.validate_patch(patch)
            self._clear_hotkey_errors()
        except Exception as e:
            self._apply_hotkey_error(str(e))

    def _schedule_apply(self) -> None:
        if self._apply_after_id is not None:
            try:
                self.after_cancel(self._apply_after_id)
            except Exception:
                pass
            self._apply_after_id = None
        self._apply_after_id = self.after(200, self._apply_now)

    def _apply_now(self) -> None:
        self._apply_after_id = None
        if self._building:
            return
        patch = self._collect_patch()
        try:
            # apply_patch 内部会 mark UoW dirty + notify_dirty（如果有变化）
            self._services.base.apply_patch(patch)
        except Exception:
            # 输入中间态可能不合法，不阻断 UI
            return

    # ---------------- watchers ----------------
    def _install_dirty_watchers(self) -> None:
        def on_any(*_args) -> None:
            if self._building:
                return
            self._validate_confirm_hotkey_live()
            self._schedule_apply()

        for v in [
            self.var_theme,
            self.var_monitor_policy_disp,

            self.var_pick_confirm_hotkey,

            self.var_avoid_mode_disp,
            self.var_avoid_delay,
            self.var_preview_follow,
            self.var_preview_offset_x,
            self.var_preview_offset_y,
            self.var_preview_anchor_disp,

            self.var_mouse_avoid,
            self.var_mouse_avoid_offset_y,
            self.var_mouse_avoid_settle_ms,

            self.var_auto_save,
            self.var_backup,
        ]:
            v.trace_add("write", on_any)

    # ---------------- UI groups ----------------
    def _build_ui_group(self, master: tb.Frame) -> None:
        lf = tb.Labelframe(master, text="界面 / 截图 / 取色确认", padding=10)
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

        tb.Label(lf, text="取色确认热键").grid(row=2, column=0, sticky="w", pady=4)
        self._hk_confirm = HotkeyEntry(lf, textvariable=self.var_pick_confirm_hotkey)
        self._hk_confirm.grid(row=2, column=1, sticky="ew", pady=4)

        tb.Label(lf, text="提示：Esc 固定为取消").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_pick_group(self, master: tb.Frame) -> None:
        lf = tb.Labelframe(master, text="取色避让 / 预览 / 鼠标避让", padding=10)
        lf.grid(row=0, column=1, sticky="nsew")
        lf.columnconfigure(1, weight=1)

        tb.Label(lf, text="窗口避让模式").grid(row=0, column=0, sticky="w", pady=4)
        tb.Combobox(
            lf,
            textvariable=self.var_avoid_mode_disp,
            values=list(_AVOID_DISP_TO_VAL.keys()),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        tb.Label(lf, text="进入延迟(ms)").grid(row=1, column=0, sticky="w", pady=4)
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

        tb.Separator(lf).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 10))

        tb.Checkbutton(lf, text="确认取色前鼠标避让（防止 hover 高亮污染颜色）", variable=self.var_mouse_avoid).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        tb.Label(lf, text="避让 Y 偏移(px)").grid(row=8, column=0, sticky="w", pady=4)
        tb.Spinbox(lf, from_=0, to=500, increment=5, textvariable=self.var_mouse_avoid_offset_y).grid(
            row=8, column=1, sticky="ew", pady=4
        )

        tb.Label(lf, text="避让后等待(ms)").grid(row=9, column=0, sticky="w", pady=4)
        tb.Spinbox(lf, from_=0, to=500, increment=10, textvariable=self.var_mouse_avoid_settle_ms).grid(
            row=9, column=1, sticky="ew", pady=4
        )

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

            self.var_pick_confirm_hotkey.set(getattr(b.pick, "confirm_hotkey", "") or "f8")

            av = b.pick.avoidance
            self.var_avoid_mode_disp.set(_AVOID_VAL_TO_DISP.get(av.mode, "隐藏主窗口"))
            self.var_avoid_delay.set(int(av.delay_ms))
            self.var_preview_follow.set(bool(av.preview_follow_cursor))
            self.var_preview_offset_x.set(int(av.preview_offset[0]))
            self.var_preview_offset_y.set(int(av.preview_offset[1]))
            self.var_preview_anchor_disp.set(_ANCHOR_VAL_TO_DISP.get(av.preview_anchor, "右下"))

            self.var_mouse_avoid.set(bool(getattr(b.pick, "mouse_avoid", True)))
            self.var_mouse_avoid_offset_y.set(int(getattr(b.pick, "mouse_avoid_offset_y", 80)))
            self.var_mouse_avoid_settle_ms.set(int(getattr(b.pick, "mouse_avoid_settle_ms", 80)))

            self.var_auto_save.set(bool(b.io.auto_save))
            self.var_backup.set(bool(b.io.backup_on_save))
        finally:
            self._building = False

        self._validate_confirm_hotkey_live()
        # dirty UI 会被 DIRTY_STATE_CHANGED 同步

    # ---------------- actions ----------------
    def _on_reload(self) -> None:
        try:
            self._services.base.reload_cmd()
            self.set_context(self._services.ctx)
            self._bus.post_payload(EventType.INFO, InfoPayload(msg="已重新加载 base.json"))
        except Exception as e:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="重新加载失败", detail=str(e)))

    def _on_save(self) -> None:
        patch = self._collect_patch()
        try:
            self._services.base.save_cmd(patch)
            self._bus.post_payload(EventType.INFO, InfoPayload(msg="base.json 已保存"))
        except Exception as e:
            self._apply_hotkey_error(str(e))
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg="保存失败", detail=str(e)))
            messagebox.showerror("保存失败", f"{e}", parent=self.winfo_toplevel())