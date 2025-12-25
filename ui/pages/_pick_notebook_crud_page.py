from __future__ import annotations

import tkinter as tk
from typing import Any

import ttkbootstrap as tb

from core.event_bus import EventBus, Event
from core.event_types import EventType
from ui.pages._record_crud_page import RecordCrudPage
from ui.widgets.scrollable_frame import ScrollableFrame


SAMPLE_DISPLAY_TO_VALUE = {"单像素": "single", "方形均值": "mean_square"}
SAMPLE_VALUE_TO_DISPLAY = {v: k for k, v in SAMPLE_DISPLAY_TO_VALUE.items()}


class PickNotebookCrudPage(RecordCrudPage):
    """
    第二轮封装（升级）：
    - request_pick_current 仍然发 PICK_REQUEST
    - 不再消费 PICK_CONFIRMED（业务更新由应用层 PickOrchestrator 做）
    - 改为消费 RECORD_UPDATED 来刷新 UI（列表/表单/dirty）
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

        # build notebook in right_body
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

        # Application-level update hook
        self._bus.subscribe(EventType.RECORD_UPDATED, self._on_record_updated)

    def request_pick_current(self) -> None:
        if not self.current_id:
            self._bus.post(EventType.ERROR, msg=f"请先选择一个{self._record_noun}")
            return
        # flush form so config is up-to-date before pick (important!)
        self._apply_form_to_current(auto_save=False)
        self._bus.post(EventType.PICK_REQUEST, context={"type": self._pick_context_type, "id": self.current_id})

    def _on_record_updated(self, ev: Event) -> None:
        """
        Payload:
          - record_type: "skill_pixel" | "point"
          - id: record id
          - source: e.g. "pick"
          - saved: bool
        """
        rt = ev.payload.get("record_type")
        rid = ev.payload.get("id")
        saved = bool(ev.payload.get("saved", False))

        if rt != self._pick_context_type:
            return
        if not isinstance(rid, str) or not rid:
            return

        # refresh row
        self.update_tree_row(rid)

        # if current is same, refresh full form from model (robust, no payload dependency)
        if self.current_id == rid:
            try:
                self._load_into_form(rid)
            except Exception:
                pass

        # dirty decision
        if saved:
            # PickOrchestrator already committed skills/points to disk.
            # Clearing is safe because request_pick_current already flushed form into model.
            self.clear_dirty()
        else:
            self.mark_dirty()

    # ----- legacy hooks retained for subclasses (may still be used elsewhere) -----
    def _apply_pick_payload_to_model(self, rid: str, payload: dict) -> bool:
        raise NotImplementedError

    def _sync_form_after_pick(self, rid: str, payload: dict) -> None:
        return