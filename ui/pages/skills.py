# File: ui/pages/skills.py
from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *

from core.event_bus import EventBus
from core.models.common import clamp_int
from core.models.skill import Skill
from core.pick.capture import ScreenCapture
from core.profiles import ProfileContext

from ui.app.notify import UiNotify
from ui.pages._record_crud_page import ColumnDef
from ui.pages._pick_notebook_crud_page import PickNotebookCrudPage, SAMPLE_DISPLAY_TO_VALUE, SAMPLE_VALUE_TO_DISPLAY
from ui.widgets.color_swatch import ColorSwatch


def rgb_to_hex(r: int, g: int, b: int) -> str:
    r = clamp_int(int(r), 0, 255)
    g = clamp_int(int(g), 0, 255)
    b = clamp_int(int(b), 0, 255)
    return f"#{r:02X}{g:02X}{b:02X}"


class SkillsPage(PickNotebookCrudPage):
    """
    Step 3-3-3:
    - 页面提示/报错走 UiNotify，不再发 EventBus 的 INFO/ERROR/STATUS
    - pick 成功提示由 PickNotebookCrudPage 内部 notify
    """

    def __init__(self, master: tk.Misc, *, ctx: ProfileContext, bus: EventBus, services, notify: UiNotify) -> None:
        if services is None:
            raise RuntimeError("SkillsPage requires services (cannot be None)")

        self._services = services
        self._cap = ScreenCapture()

        super().__init__(
            master,
            ctx=ctx,
            bus=bus,
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
            ],
            pick_context_type="skill_pixel",
            tab_names=["基本", "像素", "备注"],
        )

        # dirty UI from UoW/store broadcast
        self.enable_uow_dirty_indicator(part_key="skills")

        # debounce apply
        self._apply_after_id: str | None = None

        tab_basic = self.tabs["基本"]
        tab_pixel = self.tabs["像素"]
        tab_note = self.tabs["备注"]

        # vars
        self.var_id = tk.StringVar(value="")
        self.var_name = tk.StringVar(value="")
        self.var_enabled = tk.BooleanVar(value=True)
        self.var_trigger_key = tk.StringVar(value="")
        self.var_readbar = tk.IntVar(value=0)

        self.var_monitor = tk.StringVar(value="primary")
        # UI uses rel coords
        self.var_x = tk.IntVar(value=0)
        self.var_y = tk.IntVar(value=0)

        self.var_r = tk.IntVar(value=0)
        self.var_g = tk.IntVar(value=0)
        self.var_b = tk.IntVar(value=0)

        self.var_tol = tk.IntVar(value=0)
        self.var_sample_mode = tk.StringVar(value="单像素")
        self.var_sample_radius = tk.IntVar(value=0)

        self._build_tab_basic(tab_basic)
        self._build_tab_pixel(tab_pixel)
        self._build_tab_note(tab_note)
        self._install_dirty_watchers()

        self.refresh_tree()

    def destroy(self) -> None:
        try:
            if self._apply_after_id is not None:
                self.after_cancel(self._apply_after_id)
        except Exception:
            pass
        try:
            self._cap.close()
        except Exception:
            pass
        super().destroy()

    def set_context(self, ctx: ProfileContext) -> None:
        # switching context: cancel pending apply
        try:
            self._cancel_pending_apply()
        except Exception:
            pass

        self._ctx = ctx
        self._current_id = None
        self.refresh_tree()

    # ----- RecordCrudPage hooks -----
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
        return (
            "是" if s.enabled else "否",
            s.name,
            short,
            s.trigger.key,
            pos,
            hx,
            str(s.pixel.tolerance),
            str(s.cast.readbar_ms),
        )

    # ----- debounce apply helpers -----
    def _cancel_pending_apply(self) -> None:
        if self._apply_after_id is not None:
            try:
                self.after_cancel(self._apply_after_id)
            except Exception:
                pass
            self._apply_after_id = None

    def _schedule_apply(self) -> None:
        self._cancel_pending_apply()
        self._apply_after_id = self.after(200, lambda: self._apply_form_to_current(auto_save=False))

    # ----- form -----
    def _build_tab_basic(self, parent: tk.Misc) -> None:
        parent.columnconfigure(1, weight=1)
        tb.Label(parent, text="ID").grid(row=0, column=0, sticky="w", pady=4)
        tb.Entry(parent, textvariable=self.var_id, state="readonly").grid(row=0, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="名称").grid(row=1, column=0, sticky="w", pady=4)
        tb.Entry(parent, textvariable=self.var_name).grid(row=1, column=1, sticky="ew", pady=4)

        tb.Checkbutton(parent, text="启用", variable=self.var_enabled).grid(row=2, column=0, sticky="w", pady=(10, 4))

        tb.Label(parent, text="触发键").grid(row=3, column=0, sticky="w", pady=4)
        tb.Entry(parent, textvariable=self.var_trigger_key).grid(row=3, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="读条时间(ms)").grid(row=4, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=10, textvariable=self.var_readbar).grid(
            row=4, column=1, sticky="ew", pady=4
        )

    def _build_tab_pixel(self, parent: tk.Misc) -> None:
        for c in range(0, 6):
            parent.columnconfigure(c, weight=1)

        tb.Label(parent, text="屏幕").grid(row=0, column=0, sticky="w", pady=4)
        tb.Combobox(
            parent,
            textvariable=self.var_monitor,
            values=["primary", "all", "monitor_1", "monitor_2"],
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="X(rel)").grid(row=0, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=1, textvariable=self.var_x).grid(
            row=0, column=3, sticky="ew", pady=4
        )
        tb.Label(parent, text="Y(rel)").grid(row=0, column=4, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=1, textvariable=self.var_y).grid(
            row=0, column=5, sticky="ew", pady=4
        )

        self._swatch = ColorSwatch(parent)
        self._swatch.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 10))

        tb.Label(parent, text="R").grid(row=2, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_r).grid(
            row=2, column=1, sticky="ew", pady=4
        )
        tb.Label(parent, text="G").grid(row=2, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_g).grid(
            row=2, column=3, sticky="ew", pady=4
        )
        tb.Label(parent, text="B").grid(row=2, column=4, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_b).grid(
            row=2, column=5, sticky="ew", pady=4
        )

        tb.Label(parent, text="容差").grid(row=3, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_tol).grid(
            row=3, column=1, sticky="ew", pady=4
        )

        tb.Label(parent, text="采样模式").grid(row=4, column=0, sticky="w", pady=4)
        tb.Combobox(
            parent,
            textvariable=self.var_sample_mode,
            values=list(SAMPLE_DISPLAY_TO_VALUE.keys()),
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="半径").grid(row=4, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=50, increment=1, textvariable=self.var_sample_radius).grid(
            row=4, column=3, sticky="ew", pady=4
        )

        tb.Button(parent, text="从屏幕取色（按确认热键确认）", bootstyle=PRIMARY, command=self.request_pick_current).grid(
            row=6, column=0, columnspan=6, sticky="ew", pady=(12, 0)
        )

    def _build_tab_note(self, parent: tk.Misc) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self._txt_note = tk.Text(parent, height=10, wrap="word")
        self._txt_note.grid(row=0, column=0, sticky="nsew")
        self._txt_note.bind("<<Modified>>", self._on_note_modified)

    def _install_dirty_watchers(self) -> None:
        def on_any(*_args) -> None:
            if getattr(self, "_building_form", False):
                return
            try:
                self._swatch.set_rgb(self.var_r.get(), self.var_g.get(), self.var_b.get())
            except Exception:
                pass
            self._schedule_apply()

        for v in [
            self.var_name, self.var_enabled, self.var_trigger_key, self.var_readbar,
            self.var_monitor, self.var_x, self.var_y,
            self.var_r, self.var_g, self.var_b,
            self.var_tol, self.var_sample_mode, self.var_sample_radius,
        ]:
            v.trace_add("write", on_any)

    def _on_note_modified(self, _evt=None) -> None:
        if getattr(self, "_building_form", False):
            self._txt_note.edit_modified(False)
            return
        if self._txt_note.edit_modified():
            self._txt_note.edit_modified(False)
            self._schedule_apply()

    def _clear_form(self) -> None:
        self._cancel_pending_apply()

        self._var_title.set("未选择")
        self._building_form = True
        try:
            self.var_id.set("")
            self.var_name.set("")
            self.var_enabled.set(True)
            self.var_trigger_key.set("")
            self.var_readbar.set(0)
            self.var_monitor.set("primary")
            self.var_x.set(0)
            self.var_y.set(0)
            self.var_r.set(0)
            self.var_g.set(0)
            self.var_b.set(0)
            self.var_tol.set(0)
            self.var_sample_mode.set("单像素")
            self.var_sample_radius.set(0)
            self._txt_note.delete("1.0", "end")
            self._txt_note.edit_modified(False)
        finally:
            self._building_form = False

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
            self.var_id.set(s.id)
            self.var_name.set(s.name)
            self.var_enabled.set(bool(s.enabled))
            self.var_trigger_key.set(s.trigger.key)
            self.var_readbar.set(int(s.cast.readbar_ms))

            self.var_monitor.set(s.pixel.monitor or "primary")
            try:
                rx, ry = self._cap.abs_to_rel(int(s.pixel.vx), int(s.pixel.vy), self.var_monitor.get())
            except Exception:
                rx, ry = 0, 0
            self.var_x.set(int(rx))
            self.var_y.set(int(ry))

            self.var_r.set(int(s.pixel.color.r))
            self.var_g.set(int(s.pixel.color.g))
            self.var_b.set(int(s.pixel.color.b))
            self._swatch.set_rgb(self.var_r.get(), self.var_g.get(), self.var_b.get())

            self.var_tol.set(int(s.pixel.tolerance))
            self.var_sample_mode.set(SAMPLE_VALUE_TO_DISPLAY.get(s.pixel.sample.mode or "single", "单像素"))
            self.var_sample_radius.set(int(s.pixel.sample.radius))

            self._txt_note.delete("1.0", "end")
            self._txt_note.insert("1.0", s.note or "")
            self._txt_note.edit_modified(False)
        finally:
            self._building_form = False

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        if getattr(self, "_building_form", False) or not self._current_id:
            return True

        self._cancel_pending_apply()

        sid = self._current_id

        mon = (self.var_monitor.get() or "primary").strip() or "primary"
        rel_x = clamp_int(int(self.var_x.get()), 0, 10**9)
        rel_y = clamp_int(int(self.var_y.get()), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        from core.app.services.skills_service import SkillFormPatch

        patch = SkillFormPatch(
            name=self.var_name.get(),
            enabled=bool(self.var_enabled.get()),
            trigger_key=self.var_trigger_key.get(),
            readbar_ms=int(self.var_readbar.get()),
            monitor=mon,
            vx=int(vx),
            vy=int(vy),
            r=int(self.var_r.get()),
            g=int(self.var_g.get()),
            b=int(self.var_b.get()),
            tolerance=int(self.var_tol.get()),
            sample_mode=SAMPLE_DISPLAY_TO_VALUE.get(self.var_sample_mode.get(), "single"),
            sample_radius=int(self.var_sample_radius.get()),
            note=self._txt_note.get("1.0", "end").rstrip("\n"),
        )

        try:
            changed, _saved = self._services.skills.apply_form_patch(sid, patch, auto_save=False)
            if changed:
                self.update_tree_row(sid)
        except Exception as e:
            self._notify.error("应用表单失败", detail=str(e))
            return False

        return True

    def _find_skill(self, sid: str) -> Skill | None:
        for s in self._ctx.skills.skills:
            if s.id == sid:
                return s
        return None

    def _apply_pick_confirmed(self, rid: str, payload) -> tuple[bool, bool]:
        return self._services.skills.apply_pick_cmd(
            rid,
            vx=payload.vx,
            vy=payload.vy,
            monitor=payload.monitor,
            r=payload.r,
            g=payload.g,
            b=payload.b,
        )

    def flush_to_model(self) -> None:
        try:
            self._apply_form_to_current(auto_save=False)
        except Exception:
            pass