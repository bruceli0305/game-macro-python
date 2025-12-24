from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *

from core.app.services.skills_service import SkillsService
from core.event_bus import EventBus
from core.models.common import clamp_int
from core.models.skill import Skill
from core.profiles import ProfileContext
from ui.pages._record_crud_page import ColumnDef
from ui.pages._pick_notebook_crud_page import PickNotebookCrudPage, SAMPLE_DISPLAY_TO_VALUE, SAMPLE_VALUE_TO_DISPLAY
from ui.widgets.color_swatch import ColorSwatch


class SkillsPage(PickNotebookCrudPage):
    def __init__(self, master: tk.Misc, *, ctx: ProfileContext, bus: EventBus) -> None:
        super().__init__(
            master,
            ctx=ctx,
            bus=bus,
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

        self._svc = SkillsService(ctx_provider=lambda: self._ctx, bus=self._bus)

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
        self.var_x = tk.IntVar(value=0)  # rel
        self.var_y = tk.IntVar(value=0)  # rel

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
            self._svc.close()
        except Exception:
            pass
        super().destroy()

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._current_id = None
        self.clear_dirty()
        self.refresh_tree()

    # ----- RecordCrudPage hooks -----
    def _records(self) -> list:
        return self._ctx.skills.skills

    def _save_to_disk(self) -> bool:
        return self._svc.save()

    def _make_new_record(self) -> Skill:
        return self._svc.make_new()

    def _clone_record(self, record: Skill) -> Skill:
        return self._svc.clone(record)

    def _delete_record_by_id(self, rid: str) -> None:
        self._svc.delete_by_id(rid)

    def _record_id(self, record: Skill) -> str:
        return record.id

    def _record_title(self, record: Skill) -> str:
        return record.name

    def _record_row_values(self, s: Skill) -> tuple:
        return self._svc.row_values(s)

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
        tb.Combobox(parent, textvariable=self.var_monitor, values=["primary", "all", "monitor_1", "monitor_2"],
                    state="readonly").grid(row=0, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="X(rel)").grid(row=0, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=1, textvariable=self.var_x).grid(row=0, column=3, sticky="ew", pady=4)
        tb.Label(parent, text="Y(rel)").grid(row=0, column=4, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=1, textvariable=self.var_y).grid(row=0, column=5, sticky="ew", pady=4)

        self._swatch = ColorSwatch(parent)
        self._swatch.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 10))

        tb.Label(parent, text="R").grid(row=2, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_r).grid(row=2, column=1, sticky="ew", pady=4)
        tb.Label(parent, text="G").grid(row=2, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_g).grid(row=2, column=3, sticky="ew", pady=4)
        tb.Label(parent, text="B").grid(row=2, column=4, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_b).grid(row=2, column=5, sticky="ew", pady=4)

        tb.Label(parent, text="容差").grid(row=3, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_tol).grid(row=3, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="采样模式").grid(row=4, column=0, sticky="w", pady=4)
        tb.Combobox(parent, textvariable=self.var_sample_mode, values=list(SAMPLE_DISPLAY_TO_VALUE.keys()),
                    state="readonly").grid(row=4, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="半径").grid(row=4, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=50, increment=1, textvariable=self.var_sample_radius).grid(
            row=4, column=3, sticky="ew", pady=4
        )

        tb.Button(parent, text="从屏幕取色（左键确认）", bootstyle=PRIMARY, command=self.request_pick_current).grid(
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
            self.mark_dirty()
            try:
                self._swatch.set_rgb(self.var_r.get(), self.var_g.get(), self.var_b.get())
            except Exception:
                pass

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
            self.mark_dirty()
            self._txt_note.edit_modified(False)

    def _clear_form(self) -> None:
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
        s = self._svc.find_by_id(rid)
        if s is None:
            return
        self._current_id = rid
        short = rid[-6:] if len(rid) >= 6 else rid
        self.set_header_title(f"{s.name}  [{short}]")

        rx, ry = self._svc.load_rel_xy(s)

        self._building_form = True
        try:
            self.var_id.set(s.id)
            self.var_name.set(s.name)
            self.var_enabled.set(bool(s.enabled))
            self.var_trigger_key.set(s.trigger.key)
            self.var_readbar.set(int(s.cast.readbar_ms))

            self.var_monitor.set(s.pixel.monitor or "primary")
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
        s = self._svc.find_by_id(self._current_id)
        if s is None:
            return False

        self._svc.apply_form(
            s,
            name=self.var_name.get(),
            enabled=bool(self.var_enabled.get()),
            trigger_key=self.var_trigger_key.get(),
            readbar_ms=int(self.var_readbar.get()),
            monitor=self.var_monitor.get(),
            rel_x=int(self.var_x.get()),
            rel_y=int(self.var_y.get()),
            r=int(self.var_r.get()),
            g=int(self.var_g.get()),
            b=int(self.var_b.get()),
            tolerance=int(self.var_tol.get()),
            sample_mode=SAMPLE_DISPLAY_TO_VALUE.get(self.var_sample_mode.get(), "single"),
            sample_radius=int(self.var_sample_radius.get()),
            note=self._txt_note.get("1.0", "end").rstrip("\n"),
        )

        self.update_tree_row(s.id)

        if auto_save and self._ctx.base.io.auto_save:
            if self._save_to_disk():
                self.clear_dirty()
        return True

    # ----- pick hook -----
    def _apply_pick_payload_to_model(self, rid: str, payload: dict) -> bool:
        s = self._svc.find_by_id(rid)
        if s is None:
            return False
        self._svc.apply_pick_payload(s, payload)
        return True

    def _sync_form_after_pick(self, rid: str, payload: dict) -> None:
        self._building_form = True
        try:
            self.var_x.set(int(payload.get("x", 0)))
            self.var_y.set(int(payload.get("y", 0)))

            r = clamp_int(int(payload.get("r", 0)), 0, 255)
            g = clamp_int(int(payload.get("g", 0)), 0, 255)
            b = clamp_int(int(payload.get("b", 0)), 0, 255)
            self.var_r.set(r)
            self.var_g.set(g)
            self.var_b.set(b)
            self._swatch.set_rgb(r, g, b)

            mon = payload.get("monitor")
            if isinstance(mon, str) and mon:
                self.var_monitor.set(mon)
        finally:
            self._building_form = False