# File: ui/pages/_record_crud_page.py
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Any

import ttkbootstrap as tb
from ttkbootstrap.constants import LEFT
from tkinter import messagebox

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.payloads import (
    InfoPayload,
    ErrorPayload,
    RecordUpdatedPayload,
    RecordDeletedPayload,
    DirtyStateChangedPayload,
)


@dataclass
class ColumnDef:
    key: str
    heading: str
    width: int = 80
    anchor: str = "center"


class RecordCrudPage(tb.Frame):
    """
    Step 6 change (核心)：
    - 点击 CRUD 时不再本地插入/删除 Treeview 行
    - Treeview 的增删改只发生在“事件消费端”（例如 PickNotebookCrudPage 的 RECORD_* handler）
    - 本类仅维护一个 pending_select_id：用于新增/复制后，等事件到来再选中

    仍保留：
    - 手动保存按钮（_save_to_disk）-> 写盘（由 services.save 实现）
    - refresh_tree 作为兜底全量刷新
    - dirty UI 展示：绑定 UoW DIRTY_STATE_CHANGED（Step 4）
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

        # dirty UI state (VIEW ONLY, derived from UoW)
        self._dirty_ui = False
        self._uow_part_key: str | None = None

        # Step 6: new/dup 后等待 RECORD_UPDATED 再选中
        self._pending_select_id: str | None = None

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

        # right panel
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

    # ---------- dirty UI (VIEW ONLY) ----------
    def enable_uow_dirty_indicator(self, *, part_key: str) -> None:
        self._uow_part_key = str(part_key)
        self._bus.subscribe(EventType.DIRTY_STATE_CHANGED, self._on_dirty_state_changed)

    def _on_dirty_state_changed(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, DirtyStateChangedPayload):
            return
        key = self._uow_part_key
        if not key:
            return
        parts = set(p.parts or [])
        self._set_dirty_ui(key in parts)

    def _set_dirty_ui(self, flag: bool) -> None:
        self._dirty_ui = bool(flag)
        self._update_dirty_ui()

    def is_dirty(self) -> bool:
        return bool(self._dirty_ui)

    def _update_dirty_ui(self) -> None:
        self._var_dirty.set("未保存*" if self._dirty_ui else "")
        try:
            self._btn_save.configure(bootstyle="warning" if self._dirty_ui else "")
        except Exception:
            pass

    # 兼容旧调用：仅影响 UI，不再触碰 UoW
    def mark_dirty(self) -> None:
        self._set_dirty_ui(True)

    def clear_dirty(self) -> None:
        self._set_dirty_ui(False)

    # ---------- pending select (Step 6) ----------
    def _set_pending_select(self, rid: str | None) -> None:
        self._pending_select_id = (rid or "").strip() or None

    def consume_pending_select_if_match(self, rid: str) -> bool:
        """
        供“事件消费端”调用：如果 rid 与 pending_select_id 匹配，则消费并返回 True。
        """
        if not rid:
            return False
        if self._pending_select_id != rid:
            return False
        self._pending_select_id = None
        return True

    def try_select_id_if_exists(self, rid: str) -> None:
        """
        供“事件消费端”调用：在 update_tree_row 插入后选中它。
        """
        if not rid:
            return
        try:
            if self._tv.exists(rid):
                self._select_id(rid)
        except Exception:
            pass

    # ---------- public ----------
    @property
    def current_id(self) -> str | None:
        return self._current_id

    def set_header_title(self, text: str) -> None:
        self._var_title.set(text)

    # ---------- event hook (保留；但 PickNotebookCrudPage 返回 None) ----------
    def _record_type_key(self) -> str | None:
        return None

    def _post_record_updated(self, rid: str, *, source: str, saved: bool) -> None:
        rt = self._record_type_key()
        if not rt or not rid:
            return
        self._bus.post_payload(
            EventType.RECORD_UPDATED,
            RecordUpdatedPayload(record_type=rt, id=rid, source=source, saved=bool(saved)),
        )

    def _post_record_deleted(self, rid: str, *, source: str, saved: bool) -> None:
        rt = self._record_type_key()
        if not rt or not rid:
            return
        self._bus.post_payload(
            EventType.RECORD_DELETED,
            RecordDeletedPayload(record_type=rt, id=rid, source=source, saved=bool(saved)),
        )

    # ---------- tree helpers ----------
    def refresh_tree(self) -> None:
        selected = self._current_id
        try:
            self._tv.delete(*self._tv.get_children())
        except Exception:
            pass

        for r in self._records():
            rid = self._record_id(r)
            if rid:
                try:
                    self._tv.insert("", "end", iid=rid, values=self._record_row_values(r))
                except Exception:
                    pass

        if selected and self._tv.exists(selected):
            self._select_id(selected)
        else:
            self._select_first_if_any()

    def update_tree_row(self, rid: str) -> None:
        """
        事件消费端可调用：根据当前 model 刷新/插入对应行。
        """
        r = self._find_record_by_id(rid)
        if r is None or not rid:
            return
        try:
            if self._tv.exists(rid):
                self._tv.item(rid, values=self._record_row_values(r))
            else:
                self._tv.insert("", "end", iid=rid, values=self._record_row_values(r))
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

        # 离开旧记录：flush 到内存（services 内部标记 dirty / 发事件）
        if self._current_id is not None:
            self._apply_form_to_current(auto_save=False)

        self._load_into_form(rid)

    # ---------- CRUD (Step 6: no local tree ops) ----------
    def _on_add(self) -> None:
        self._apply_form_to_current(auto_save=False)

        rec = self._make_new_record()
        rid = self._record_id(rec)
        if not rid:
            # 极端兜底
            self.refresh_tree()
            return

        # 等 RECORD_UPDATED 来了再选中
        self._set_pending_select(rid)

        self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已新增{self._record_noun}: {rid[-6:]}"))

    def _on_duplicate(self) -> None:
        sel = self._tv.selection()
        if not sel:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"请先选择要复制的{self._record_noun}"))
            return

        self._apply_form_to_current(auto_save=False)

        rid = sel[0]
        src = self._find_record_by_id(rid)
        if src is None:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"源{self._record_noun}不存在"))
            return

        clone = self._clone_record(src)
        new_id = self._record_id(clone)
        if not new_id:
            self.refresh_tree()
            return

        self._set_pending_select(new_id)

        self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已复制{self._record_noun}: {new_id[-6:]}"))

    def _on_delete(self) -> None:
        sel = self._tv.selection()
        if not sel:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"请先选择要删除的{self._record_noun}"))
            return

        rid = sel[0]
        rec = self._find_record_by_id(rid)
        if rec is None:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"{self._record_noun}不存在"))
            return

        ok = messagebox.askyesno(
            f"删除{self._record_noun}",
            f"确认删除该{self._record_noun}？\n\n{self._record_title(rec)}\nID: {rid}",
            parent=self.winfo_toplevel(),
        )
        if not ok:
            return

        # Step 6: 只发命令；删行/选中由 RECORD_DELETED 事件处理
        try:
            self._delete_record_by_id(rid)
        except Exception as e:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"删除失败", detail=str(e)))
            return

        # 若 pending 正好是这个 id，清掉
        if self._pending_select_id == rid:
            self._pending_select_id = None

        self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"已删除{self._record_noun}: {rid[-6:]}"))

    def _on_save_clicked(self) -> None:
        if not self._apply_form_to_current(auto_save=False):
            return
        if self._save_to_disk():
            rid = self.current_id
            if isinstance(rid, str) and rid:
                self._post_record_updated(rid, source="manual_save", saved=True)
            self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"{self._record_noun}已保存"))

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