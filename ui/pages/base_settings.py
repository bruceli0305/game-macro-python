# File: ui/pages/base_settings.py
from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import messagebox

from core.models.common import clamp_int
from core.profiles import ProfileContext
from core.app.services.base_settings_service import BaseSettingsPatch

from ui.app.notify import UiNotify
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
    Step 3-3-3-3-3:
    - BaseSettingsService 不再发 EventBus 的 INFO/STATUS/UI_THEME_CHANGE
    - 页面用 UiNotify 提示，并在保存/重载后直接 apply_theme
    - 阶段二：脏状态 UI 不再监听 EventBus.DIRTY_STATE_CHANGED，而是直接订阅 AppStore.dirty
    - 阶段三：完全移除对 EventBus 的依赖
    """

    def __init__(self, master: tk.Misc, *, ctx: ProfileContext, services, notify: UiNotify) -> None:
        super().__init__(master)
        if services is None:
            raise RuntimeError("BaseSettingsPage requires services (cannot be None)")

        self._ctx = ctx
        self._services = services
        self._notify = notify

        self._building = False
        self._dirty_ui = False
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

        self.var_pick_confirm_hotkey = tk.StringVar(value=getattr(b.pick, "confirm_hotkey", "") or "f8")

        av = b.pick.avoidance
        self.var_avoid_mode_disp = tk.StringVar(value=_AVOID_VAL_TO_DISP.get(av.mode, "隐藏主窗口"))
        self.var_avoid_delay = tk.IntVar(value=int(av.delay_ms))
        self.var_preview_follow = tk.BooleanVar(value=bool(av.preview_follow_cursor))
        self.var_preview_offset_x = tk.IntVar(value=int(av.preview_offset[0]))
        self.var_preview_offset_y = tk.IntVar(value=int(av.preview_offset[1]))
        self.var_preview_anchor_disp = tk.StringVar(value=_ANCHOR_VAL_TO_DISP.get(av.preview_anchor, "右下"))

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

        # 脏状态 UI：直接订阅 AppStore，而不是 EventBus.DIRTY_STATE_CHANGED
        try:
            self._services.store.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

        self._set_dirty_ui(False)

    def _set_dirty_ui(self, flag: bool) -> None:
        self._dirty_ui = bool(flag)
        self._var_dirty.set("未保存*" if self._dirty_ui else "")

    def _on_store_dirty(self, parts) -> None:
        """
        AppStore.dirty 订阅回调：parts 是当前脏的 part 集合（如 {"base", "skills"}）。
        """
        try:
            parts_set = set(parts or [])
        except Exception:
            parts_set = set()
        self._set_dirty_ui("base" in parts_set)

    # --- standardized flush ---
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
        s = (msg or "").strip()
        self._clear_hotkey_errors()

        if "confirm_hotkey:" in s:
            try:
                self._hk_confirm.set_error(s.split(":", 1)[1].strip())
            except Exception:
                pass
            return

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
            self._services.base.apply_patch(patch)
        except Exception:
            return

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

    # ---------------- actions ----------------
    def _on_reload(self) -> None:
        try:
            self._services.base.reload_cmd()
            self.set_context(self._services.ctx)
            self._notify.apply_theme(self._services.ctx.base.ui.theme)
            self._notify.info("已重新加载 base.json")
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))

    def _on_save(self) -> None:
        patch = self._collect_patch()
        try:
            saved = self._services.base.save_cmd(patch)
            if not saved:
                self._notify.status_msg("未检测到更改", ttl_ms=2000)
                return

            # apply theme immediately
            self._notify.apply_theme(self._services.ctx.base.ui.theme)
            self._notify.info("base.json 已保存")
        except Exception as e:
            self._apply_hotkey_error(str(e))
            self._notify.error("保存失败", detail=str(e))
            messagebox.showerror("保存失败", f"{e}", parent=self.winfo_toplevel())