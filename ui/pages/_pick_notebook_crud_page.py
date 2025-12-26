# File: ui/pages/_pick_notebook_crud_page.py
from __future__ import annotations

import tkinter as tk
from typing import Any

import ttkbootstrap as tb

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.payloads import PickRequestPayload, PickContextRef, PickConfirmedPayload, ErrorPayload
from ui.pages._record_crud_page import RecordCrudPage
from ui.widgets.scrollable_frame import ScrollableFrame


SAMPLE_DISPLAY_TO_VALUE = {"单像素": "single", "方形均值": "mean_square"}
SAMPLE_VALUE_TO_DISPLAY = {v: k for k, v in SAMPLE_DISPLAY_TO_VALUE.items()}


class PickNotebookCrudPage(RecordCrudPage):
    """
    Step 2:
    - 取色确认由页面消费 PICK_CONFIRMED 并直接应用到当前记录（不再走 PickOrchestrator + RECORD_UPDATED）
    - CRUD/表单刷新也不依赖 RECORD_* 事件
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

        self._bus.subscribe(EventType.PICK_CONFIRMED, self._on_pick_confirmed)

    def request_pick_current(self) -> None:
        if not self.current_id:
            self._bus.post_payload(EventType.ERROR, ErrorPayload(msg=f"请先选择一个{self._record_noun}"))
            return

        # flush current form so pick is applied to the correct (latest) record state
        self._apply_form_to_current(auto_save=False)

        self._bus.post_payload(
            EventType.PICK_REQUEST,
            PickRequestPayload(context=PickContextRef(type=self._pick_context_type, id=self.current_id)),
        )

    def _on_pick_confirmed(self, ev: Event) -> None:
        p = ev.payload
        if not isinstance(p, PickConfirmedPayload):
            return

        ctx_ref = p.context
        if ctx_ref.type != self._pick_context_type:
            return

        rid = ctx_ref.id
        if not rid:
            return

        # Apply to model via derived class (calls service.apply_pick_cmd)
        applied, saved = self._apply_pick_confirmed(rid, p)

        if not applied:
            return

        # Update row + reload form (pick is an explicit action; reload is OK)
        self.update_tree_row(rid)
        if self.current_id == rid:
            try:
                self._load_into_form(rid)
            except Exception:
                pass

        # UI message (optional)
        from core.events.payloads import StatusPayload, InfoPayload
        if p.hex:
            if saved:
                self._bus.post_payload(EventType.INFO, InfoPayload(msg=f"取色已应用并保存: {p.hex}"))
            else:
                self._bus.post_payload(EventType.STATUS, StatusPayload(msg=f"取色已应用(未保存): {p.hex}"))

    def _apply_pick_confirmed(self, rid: str, payload: PickConfirmedPayload) -> tuple[bool, bool]:
        """
        Must return (applied, saved). Implement in SkillsPage / PointsPage.
        """
        raise NotImplementedError