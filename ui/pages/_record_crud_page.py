from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Any

import ttkbootstrap as tb
from ttkbootstrap.constants import LEFT, X
from tkinter import messagebox  # 修复：不要用 tk.messagebox

from core.event_bus import EventBus
from core.event_types import EventType


@dataclass
class ColumnDef:
    key: str
    heading: str
    width: int = 80
    anchor: str = "center"


class RecordCrudPage(tb.Frame):
    """
    公共封装（第一轮基类，第二轮继续保留）：
    - 左侧 Treeview CRUD（新增/复制/删除/保存）
    - 选择切换时自动 apply 当前表单（auto_save 可选）
    - dirty 管理 + auto_save
    - Treeview 行更新/全量刷新

    子类必须实现 hooks：
      - _records() -> list
      - _save_to_disk() -> bool
      - _make_new_record() -> record
      - _clone_record(record) -> record
      - _delete_record_by_id(record_id) -> None
      - _record_id(record) -> str
      - _record_title(record) -> str
      - _record_row_values(record) -> tuple
      - _load_into_form(record_id) -> None
      - _apply_form_to_current(auto_save: bool) -> bool
      - _clear_form() -> None
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        ctx: Any,
        bus: EventBus,
        page_title: str,
        record_noun: str,
        columns: list[ColumnDef],
    ) -> None:
        super().__init__(master)
        self._ctx = ctx
        self._bus = bus
        self._page_title_text = page_title
        self._record_noun = record_noun
        self._columns = columns

        self._current_id: str | None = None
        self._suppress_select = False
        self._dirty_disk = False

        # layout
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        tb.Label(self, text=self._page_title_text, font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        # left panel
        left = tb.Frame(self)
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 12))
        left.rowconfigure(1, weight=1)

        toolbar = tb.Frame(left)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        tb.Button(toolbar, text="新增", bootstyle="success", command=self._on_add).pack(side=LEFT)
        tb.Button(toolbar, text="复制", command=self._on_duplicate).pack(side=LEFT, padx=(6, 0))
        tb.Button(toolbar, text="删除", bootstyle="danger", command=self._on_delete).pack(side=LEFT, padx=(6, 0))
        self._btn_save = tb.Button(toolbar, text="保存", command=self._on_save_clicked)
        self._btn_save.pack(side=LEFT, padx=(12, 0))

        self._tv = tb.Treeview(left, columns=[c.key for c in self._columns], show="headings", height=18)
        self._tv.grid(row=1, column=0, sticky="nsew")

        for c in self._columns:
            self._tv.heading(c.key, text=c.heading)
            self._tv.column(c.key, width=c.width, anchor=c.anchor)

        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # right panel header + body placeholder (子类去构建 Notebook)
        right = tb.Frame(self)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        header = tb.Frame(right)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)

        self._var_title = tk.StringVar(value="未选择")
        tb.Label(header, textvariable=self._var_title, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")

        self._var_dirty = tk.StringVar(value="")
        tb.Label(header, textvariable=self._var_dirty, bootstyle="warning").grid(row=0, column=1, sticky="e")

        self.right_body = tb.Frame(right)
        self.right_body.grid(row=1, column=0, sticky="nsew")
        self.right_body.columnconfigure(0, weight=1)
        self.right_body.rowconfigure(0, weight=1)

        self._update_dirty_ui()

    # ---------- public ----------
    def is_dirty(self) -> bool:
        return bool(self._dirty_disk)

    @property
    def current_id(self) -> str | None:
        return self._current_id

    def set_header_title(self, text: str) -> None:
        self._var_title.set(text)

    # ---------- dirty ----------
    def mark_dirty(self) -> None:
        self._dirty_disk = True
        self._update_dirty_ui()

    def clear_dirty(self) -> None:
        self._dirty_disk = False
        self._update_dirty_ui()

    def _update_dirty_ui(self) -> None:
        self._var_dirty.set("未保存*" if self._dirty_disk else "")
        try:
            self._btn_save.configure(bootstyle="warning" if self._dirty_disk else "")
        except Exception:
            pass

    # ---------- tree helpers ----------
    def refresh_tree(self) -> None:
        selected = self._current_id
        self._tv.delete(*self._tv.get_children())

        for r in self._records():
            rid = self._record_id(r)
            if rid:
                self._tv.insert("", "end", iid=rid, values=self._record_row_values(r))

        if selected and self._tv.exists(selected):
            self._select_id(selected)
        else:
            self._select_first_if_any()

    def update_tree_row(self, rid: str) -> None:
        r = self._find_record_by_id(rid)
        if r is None or not rid:
            return
        try:
            if self._tv.exists(rid):
                self._tv.item(rid, values=self._record_row_values(r))
        except Exception:
            pass

    def _select_first_if_any(self) -> None:
        items = self._tv.get_children()
        if not items:
            self._current_id = None
            self._var_title.set("未选择")
            self._clear_form()
            return
        self._select_id(items[0])

    def _select_id(self, rid: str) -> None:
        self._suppress_select = True
        try:
            self._tv.selection_set(rid)
            self._tv.focus(rid)
        finally:
            self._suppress_select = False
        self._load_into_form(rid)

    def _on_select(self, _evt=None) -> None:
        if self._suppress_select:
            return
        sel = self._tv.selection()
        if not sel:
            return
        rid = sel[0]
        if self._current_id == rid:
            return

        if self._current_id is not None:
            self._apply_form_to_current(auto_save=True)

        self._load_into_form(rid)

    # ---------- CRUD ----------
    def _on_add(self) -> None:
        self._apply_form_to_current(auto_save=True)

        rec = self._make_new_record()
        self._records().append(rec)
        rid = self._record_id(rec)

        self.refresh_tree()
        if rid:
            self._select_id(rid)

        self.mark_dirty()
        self._auto_save_if_needed()
        self._bus.post(EventType.INFO, msg=f"已新增{self._record_noun}: {rid[-6:] if rid else ''}")

    def _on_duplicate(self) -> None:
        sel = self._tv.selection()
        if not sel:
            self._bus.post(EventType.ERROR, msg=f"请先选择要复制的{self._record_noun}")
            return

        self._apply_form_to_current(auto_save=True)

        rid = sel[0]
        src = self._find_record_by_id(rid)
        if src is None:
            self._bus.post(EventType.ERROR, msg=f"源{self._record_noun}不存在")
            return

        clone = self._clone_record(src)
        self._records().append(clone)

        new_id = self._record_id(clone)
        self.refresh_tree()
        if new_id:
            self._select_id(new_id)

        self.mark_dirty()
        self._auto_save_if_needed()
        self._bus.post(EventType.INFO, msg=f"已复制{self._record_noun}: {new_id[-6:] if new_id else ''}")

    def _on_delete(self) -> None:
        sel = self._tv.selection()
        if not sel:
            self._bus.post(EventType.ERROR, msg=f"请先选择要删除的{self._record_noun}")
            return

        rid = sel[0]
        rec = self._find_record_by_id(rid)
        if rec is None:
            self._bus.post(EventType.ERROR, msg=f"{self._record_noun}不存在")
            return

        ok = messagebox.askyesno(
            f"删除{self._record_noun}",
            f"确认删除该{self._record_noun}？\n\n{self._record_title(rec)}\nID: {rid}",
            parent=self.winfo_toplevel(),
        )
        if not ok:
            return

        self._delete_record_by_id(rid)
        self.refresh_tree()

        self.mark_dirty()
        self._auto_save_if_needed()
        self._bus.post(EventType.INFO, msg=f"已删除{self._record_noun}: {rid[-6:]}")

    def _on_save_clicked(self) -> None:
        if not self._apply_form_to_current(auto_save=False):
            return
        if self._save_to_disk():
            self.clear_dirty()
            self._bus.post(EventType.INFO, msg=f"{self._record_noun}已保存")

    def _auto_save_if_needed(self) -> None:
        try:
            if bool(self._ctx.base.io.auto_save):
                if self._save_to_disk():
                    self.clear_dirty()
        except Exception:
            pass

    # ---------- record lookup ----------
    def _find_record_by_id(self, rid: str) -> Any | None:
        for r in self._records():
            if self._record_id(r) == rid:
                return r
        return None

    # ---------- hooks ----------
    def _records(self) -> list:
        raise NotImplementedError

    def _save_to_disk(self) -> bool:
        raise NotImplementedError

    def _make_new_record(self) -> Any:
        raise NotImplementedError

    def _clone_record(self, record: Any) -> Any:
        raise NotImplementedError

    def _delete_record_by_id(self, rid: str) -> None:
        raise NotImplementedError

    def _record_id(self, record: Any) -> str:
        raise NotImplementedError

    def _record_title(self, record: Any) -> str:
        raise NotImplementedError

    def _record_row_values(self, record: Any) -> tuple:
        raise NotImplementedError

    def _load_into_form(self, rid: str) -> None:
        raise NotImplementedError

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        raise NotImplementedError

    def _clear_form(self) -> None:
        raise NotImplementedError