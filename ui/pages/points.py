from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *

from core.event_bus import EventBus
from core.event_types import EventType
from core.io.json_store import now_iso_utc
from core.models.common import clamp_int
from core.models.point import Point
from core.models.skill import ColorRGB
from core.pick.capture import ScreenCapture
from core.profiles import ProfileContext
from ui.pages._record_crud_page import ColumnDef
from ui.pages._pick_notebook_crud_page import PickNotebookCrudPage, SAMPLE_DISPLAY_TO_VALUE, SAMPLE_VALUE_TO_DISPLAY
from ui.widgets.color_swatch import ColorSwatch


def rgb_to_hex(r: int, g: int, b: int) -> str:
    r = clamp_int(int(r), 0, 255)
    g = clamp_int(int(g), 0, 255)
    b = clamp_int(int(b), 0, 255)
    return f"#{r:02X}{g:02X}{b:02X}"


class PointsPage(PickNotebookCrudPage):
    def __init__(self, master: tk.Misc, *, ctx: ProfileContext, bus: EventBus, services=None) -> None:
        super().__init__(
            master,
            ctx=ctx,
            bus=bus,
            page_title="取色点位配置",
            record_noun="点位",
            columns=[
                ColumnDef("name", "名称", 150, "w"),
                ColumnDef("idshort", "ID", 80, "w"),
                ColumnDef("monitor", "屏幕", 80, "center"),
                ColumnDef("pos", "坐标", 90, "center"),
                ColumnDef("hex", "颜色", 80, "center"),
                ColumnDef("captured_at", "采集时间", 160, "w"),
            ],
            pick_context_type="point",
            tab_names=["基本", "颜色&采样", "备注"],
        )

        self._services = services
        self._cap = ScreenCapture()

        tab_basic = self.tabs["基本"]
        tab_color = self.tabs["颜色&采样"]
        tab_note = self.tabs["备注"]

        self.var_id = tk.StringVar(value="")
        self.var_name = tk.StringVar(value="")
        self.var_monitor = tk.StringVar(value="primary")

        # UI 使用 rel 坐标
        self.var_x = tk.IntVar(value=0)
        self.var_y = tk.IntVar(value=0)

        self.var_r = tk.IntVar(value=0)
        self.var_g = tk.IntVar(value=0)
        self.var_b = tk.IntVar(value=0)

        self.var_captured_at = tk.StringVar(value="")
        self.var_sample_mode = tk.StringVar(value="单像素")
        self.var_sample_radius = tk.IntVar(value=0)

        self._build_tab_basic(tab_basic)
        self._build_tab_color(tab_color)
        self._build_tab_note(tab_note)
        self._install_dirty_watchers()

        self.refresh_tree()

    def destroy(self) -> None:
        try:
            self._cap.close()
        except Exception:
            pass
        super().destroy()

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._current_id = None
        self.clear_dirty()
        self.refresh_tree()

    # --- UoW dirty bridge ---
    def mark_dirty(self) -> None:
        super().mark_dirty()
        if self._services is not None:
            try:
                self._services.uow.mark_dirty("points")
                self._services.notify_dirty()
            except Exception:
                pass

    def clear_dirty(self) -> None:
        super().clear_dirty()
        if self._services is not None:
            try:
                self._services.uow.clear_dirty("points")
                self._services.notify_dirty()
            except Exception:
                pass

    # ----- RecordCrudPage hooks -----
    def _records(self) -> list:
        return self._ctx.points.points

    def _save_to_disk(self) -> bool:
        try:
            if self._services is not None:
                self._services.points.save(backup=self._ctx.base.io.backup_on_save)
                self._services.notify_dirty()
            else:
                self._ctx.points_repo.save(self._ctx.points, backup=self._ctx.base.io.backup_on_save)
            return True
        except Exception as e:
            self._bus.post(EventType.ERROR, msg=f"保存 points.json 失败: {e}")
            return False
    def _make_new_record(self) -> Point:
        if self._services is not None:
            return self._services.points.create_point_cmd(name="新点位")

        pid = self._ctx.idgen.next_id()
        p = Point(
            id=pid,
            name="新点位",
            monitor="primary",
            vx=0,
            vy=0,
            color=ColorRGB(0, 0, 0),
            captured_at=now_iso_utc(),
        )
        p.sample.mode = "single"
        p.sample.radius = 0
        return p
    def _clone_record(self, record: Point) -> Point:
        if self._services is not None:
            clone = self._services.points.clone_point_cmd(record.id)
            if clone is not None:
                return clone

        new_id = self._ctx.idgen.next_id()
        clone = Point.from_dict(record.to_dict())
        clone.id = new_id
        clone.name = f"{record.name} (副本)"
        clone.captured_at = now_iso_utc()
        return clone
    def _delete_record_by_id(self, rid: str) -> None:
        if self._services is not None:
            self._services.points.delete_point_cmd(rid)
            return
        self._ctx.points.points = [x for x in self._ctx.points.points if x.id != rid]
    def _record_id(self, record: Point) -> str:
        return record.id

    def _store_add_record(self, record) -> None:
        if self._services is None:
            self._ctx.points.points.append(record)

    def _record_title(self, record: Point) -> str:
        return record.name

    def _record_row_values(self, p: Point) -> tuple:
        pid = p.id or ""
        short = pid[-6:] if len(pid) >= 6 else pid

        try:
            rx, ry = self._cap.abs_to_rel(int(p.vx), int(p.vy), p.monitor or "primary")
        except Exception:
            rx, ry = int(p.vx), int(p.vy)

        pos = f"({rx},{ry})"
        hx = rgb_to_hex(p.color.r, p.color.g, p.color.b)
        return (p.name, short, p.monitor, pos, hx, p.captured_at)

    # ----- form -----
    def _build_tab_basic(self, parent: tk.Misc) -> None:
        parent.columnconfigure(1, weight=1)

        tb.Label(parent, text="ID").grid(row=0, column=0, sticky="w", pady=4)
        tb.Entry(parent, textvariable=self.var_id, state="readonly").grid(row=0, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="名称").grid(row=1, column=0, sticky="w", pady=4)
        tb.Entry(parent, textvariable=self.var_name).grid(row=1, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="屏幕").grid(row=2, column=0, sticky="w", pady=4)
        tb.Combobox(parent, textvariable=self.var_monitor, values=["primary", "all", "monitor_1", "monitor_2"],
                    state="readonly").grid(row=2, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="X(rel)").grid(row=3, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=1, textvariable=self.var_x).grid(row=3, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="Y(rel)").grid(row=4, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=9999999, increment=1, textvariable=self.var_y).grid(row=4, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="captured_at").grid(row=5, column=0, sticky="w", pady=4)
        tb.Entry(parent, textvariable=self.var_captured_at).grid(row=5, column=1, sticky="ew", pady=4)

    def _build_tab_color(self, parent: tk.Misc) -> None:
        for c in range(0, 6):
            parent.columnconfigure(c, weight=1)

        self._swatch = ColorSwatch(parent)
        self._swatch.grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))

        tb.Label(parent, text="R").grid(row=1, column=0, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_r).grid(row=1, column=1, sticky="ew", pady=4)
        tb.Label(parent, text="G").grid(row=1, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_g).grid(row=1, column=3, sticky="ew", pady=4)
        tb.Label(parent, text="B").grid(row=1, column=4, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=255, increment=1, textvariable=self.var_b).grid(row=1, column=5, sticky="ew", pady=4)

        tb.Label(parent, text="采样模式").grid(row=2, column=0, sticky="w", pady=4)
        tb.Combobox(parent, textvariable=self.var_sample_mode, values=list(SAMPLE_DISPLAY_TO_VALUE.keys()),
                    state="readonly").grid(row=2, column=1, sticky="ew", pady=4)

        tb.Label(parent, text="半径").grid(row=2, column=2, sticky="w", pady=4)
        tb.Spinbox(parent, from_=0, to=50, increment=1, textvariable=self.var_sample_radius).grid(
            row=2, column=3, sticky="ew", pady=4
        )

        tb.Button(parent, text="从屏幕取色（左键确认）", bootstyle=PRIMARY, command=self.request_pick_current).grid(
            row=3, column=0, columnspan=6, sticky="ew", pady=(12, 0)
        )

        tb.Button(parent, text="更新时间(captured_at=now)", command=self._touch_time).grid(
            row=4, column=0, columnspan=6, sticky="ew", pady=(8, 0)
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
            self.var_name, self.var_monitor, self.var_x, self.var_y,
            self.var_r, self.var_g, self.var_b,
            self.var_captured_at, self.var_sample_mode, self.var_sample_radius,
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
        self.set_header_title("未选择")
        self._building_form = True
        try:
            self.var_id.set("")
            self.var_name.set("")
            self.var_monitor.set("primary")
            self.var_x.set(0)
            self.var_y.set(0)
            self.var_r.set(0)
            self.var_g.set(0)
            self.var_b.set(0)
            self.var_captured_at.set("")
            self.var_sample_mode.set("单像素")
            self.var_sample_radius.set(0)
            self._txt_note.delete("1.0", "end")
            self._txt_note.edit_modified(False)
        finally:
            self._building_form = False

    def _load_into_form(self, rid: str) -> None:
        p = self._find_point(rid)
        if p is None:
            return
        self._current_id = rid
        short = rid[-6:] if len(rid) >= 6 else rid
        self.set_header_title(f"{p.name}  [{short}]")

        self._building_form = True
        try:
            self.var_id.set(p.id)
            self.var_name.set(p.name)
            self.var_monitor.set(p.monitor or "primary")

            try:
                rx, ry = self._cap.abs_to_rel(int(p.vx), int(p.vy), self.var_monitor.get())
            except Exception:
                rx, ry = 0, 0
            self.var_x.set(int(rx))
            self.var_y.set(int(ry))

            self.var_r.set(int(p.color.r))
            self.var_g.set(int(p.color.g))
            self.var_b.set(int(p.color.b))
            self._swatch.set_rgb(self.var_r.get(), self.var_g.get(), self.var_b.get())

            self.var_captured_at.set(p.captured_at or "")
            self.var_sample_mode.set(SAMPLE_VALUE_TO_DISPLAY.get(p.sample.mode or "single", "单像素"))
            self.var_sample_radius.set(int(p.sample.radius))

            self._txt_note.delete("1.0", "end")
            self._txt_note.insert("1.0", p.note or "")
            self._txt_note.edit_modified(False)
        finally:
            self._building_form = False

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        if getattr(self, "_building_form", False) or not self._current_id:
            return True

        pid = self._current_id

        mon = (self.var_monitor.get() or "primary").strip() or "primary"
        rel_x = clamp_int(int(self.var_x.get()), 0, 10**9)
        rel_y = clamp_int(int(self.var_y.get()), 0, 10**9)
        try:
            vx, vy = self._cap.rel_to_abs(rel_x, rel_y, mon)
        except Exception:
            vx, vy = rel_x, rel_y

        from core.app.services.points_service import PointFormPatch

        patch = PointFormPatch(
            name=self.var_name.get(),
            monitor=mon,
            vx=int(vx),
            vy=int(vy),
            r=int(self.var_r.get()),
            g=int(self.var_g.get()),
            b=int(self.var_b.get()),
            captured_at=self.var_captured_at.get(),
            sample_mode=SAMPLE_DISPLAY_TO_VALUE.get(self.var_sample_mode.get(), "single"),
            sample_radius=int(self.var_sample_radius.get()),
            note=self._txt_note.get("1.0", "end").rstrip("\n"),
        )

        if self._services is not None:
            try:
                changed, saved = self._services.points.apply_form_patch(pid, patch, auto_save=bool(auto_save))
            except Exception as e:
                self._bus.post(EventType.ERROR, msg=f"应用表单失败: {e}")
                return False

            if not changed:
                return True

            self.update_tree_row(pid)
            if saved:
                self.clear_dirty()
            else:
                self.mark_dirty()
            return True

        return True
        
    def _find_point(self, pid: str) -> Point | None:
        for p in self._ctx.points.points:
            if p.id == pid:
                return p
        return None

    # ----- pick hook -----
    def _apply_pick_payload_to_model(self, rid: str, payload: dict) -> bool:
        p = self._find_point(rid)
        if p is None:
            return False

        if "vx" in payload and "vy" in payload:
            vx = int(payload.get("vx", 0))
            vy = int(payload.get("vy", 0))
        else:
            vx = int(payload.get("abs_x", 0))
            vy = int(payload.get("abs_y", 0))

        r = clamp_int(int(payload.get("r", 0)), 0, 255)
        g = clamp_int(int(payload.get("g", 0)), 0, 255)
        b = clamp_int(int(payload.get("b", 0)), 0, 255)

        p.vx, p.vy = vx, vy
        mon = payload.get("monitor")
        if isinstance(mon, str) and mon:
            p.monitor = mon
        p.color = ColorRGB(r=r, g=g, b=b)
        p.captured_at = now_iso_utc()
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

            self.var_captured_at.set(now_iso_utc())

            mon = payload.get("monitor")
            if isinstance(mon, str) and mon:
                self.var_monitor.set(mon)
        finally:
            self._building_form = False

    def _touch_time(self) -> None:
        self.var_captured_at.set(now_iso_utc())
        self.mark_dirty()
        self._apply_form_to_current(auto_save=True)
    def flush_to_model(self) -> None:
        try:
            self._apply_form_to_current(auto_save=False)
        except Exception:
            pass