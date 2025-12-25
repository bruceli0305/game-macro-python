# File: ui/pages/_pick_notebook_crud_page.py
from __future__ import annotations

import tkinter as tk
from typing import Any

import ttkbootstrap as tb

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.payloads import (
    RecordUpdatedPayload,
    RecordDeletedPayload,
    PickRequestPayload,
    PickContextRef,
    ErrorPayload,
)
from ui.pages._record_crud_page import RecordCrudPage
from ui.widgets.scrollable_frame import ScrollableFrame


SAMPLE_DISPLAY_TO_VALUE = {"单像素": "single", "方形均值": "mean_square"}
SAMPLE_VALUE_TO_DISPLAY = {v: k for k, v in SAMPLE_DISPLAY_TO_VALUE.items()}


class PickNotebookCrudPage(RecordCrudPage):
    """
    Step 6:
    - CRUD 点击时不再本地插入/删除行（由 RecordCrudPage 做到）
    - 本类作为“事件消费端”：
        - RECORD_UPDATED: update_tree_row + (必要时) select pending + (非 form) reload form
        - RECORD_DELETED: delete row + 处理选中
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        ctx: Any,
        bus: EventBus,
        page_title: str,
        record_noun: str,
        columns,
        pick_context_type: str,   # "skill_pixel" | "point"
        tab_names: list[str],
    ) -> None:
        super().__init__(
            master,
            ctx=ctx,
            bus=bus,
            page_title=page_title,
            record_noun=record_noun,
            columns=columns,
        )
        self._pick_context_type = pick_context_type

        sf = ScrollableFrame(self.right_body, padding=0)
        sf.grid(row=0, column=0, sticky="nsew")
        container = sf.inner
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self.nb = tb.Notebook(container)
        self.nb.grid(row=0, column=0, sticky="nsew")

        self.tabs: dict[str, tb.Frame] = {}
        for name in tab_names:
            tab = tb.Frame(self.nb, padding=10)
            self.nb.add(tab, text=name)
            self.tabs[name] = tab

        self._bus.subscribe(EventType.RECORD_UPDATED, self._on_record_updated)
        self._bus.subscribe(EventType.RECORD_DELETED, self._on_record_deleted)

    def _record_type_key(self) -> str | None:
        return None

    def request_pick_current(self) -> None:
        if not self.current_id:
            self._bus.post_payload(
                EventType.ERROR,
                ErrorPayload(msg=f"请先选择一个{self._record_noun}"),
            )
            return

        self._apply_form_to_current(auto_save=False)

        self._bus.post_payload(
            EventType.PICK_REQUEST,
            PickRequestPayload(
                context=PickContextRef(type=self._pick_context_type, id=self.current_id)
            ),
        )

    def _on_record_updated(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, RecordUpdatedPayload):
            return
        if p.record_type != self._pick_context_type:
            return

        rid = p.id
        if not rid:
            return

        # 1) 插入/刷新 row（此处是唯一刷新来源）
        self.update_tree_row(rid)

        # 2) Step 6: 如果是 pending select，则在 row 确保存在后选中
        if self.consume_pending_select_if_match(rid):
            self.try_select_id_if_exists(rid)
            return

        # 3) Step 5: form 事件不 reload 表单（避免打断输入）
        if self.current_id == rid:
            src = (p.source or "").strip().lower()
            if src != "form":
                try:
                    self._load_into_form(rid)
                except Exception:
                    pass

    def _on_record_deleted(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, RecordDeletedPayload):
            return
        if p.record_type != self._pick_context_type:
            return

        rid = p.id
        if not rid:
            return

        is_current = (self.current_id == rid)

        # 删除 row（事件消费端执行）
        try:
            if self._tv.exists(rid):
                self._tv.delete(rid)
        except Exception:
            pass

        # 若删的是当前选中，选中一个合理项
        if is_current:
            self._select_first_if_any()