from __future__ import annotations

import tkinter as tk
from typing import Any

import ttkbootstrap as tb

from core.event_bus import EventBus, Event
from ui.pages._record_crud_page import RecordCrudPage
from ui.widgets.scrollable_frame import ScrollableFrame


SAMPLE_DISPLAY_TO_VALUE = {"单像素": "single", "方形均值": "mean_square"}
SAMPLE_VALUE_TO_DISPLAY = {v: k for k, v in SAMPLE_DISPLAY_TO_VALUE.items()}


class PickNotebookCrudPage(RecordCrudPage):
    """
    第二轮封装：
    - 统一右侧：ScrollableFrame + Notebook + tabs 字典
    - 统一 pick：request_pick_current + PICK_CONFIRMED 过滤分发（按 context.type）
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

        # pick event hook
        self._bus.subscribe("PICK_CONFIRMED", self._on_pick_confirmed_event)

    def request_pick_current(self) -> None:
        if not self.current_id:
            self._bus.post("ERROR", msg=f"请先选择一个{self._record_noun}")
            return
        # flush form so sample/monitor etc are up-to-date
        self._apply_form_to_current(auto_save=False)
        self._bus.post("PICK_REQUEST", context={"type": self._pick_context_type, "id": self.current_id})

    def _on_pick_confirmed_event(self, ev: Event) -> None:
        ctx = ev.payload.get("context")
        if not isinstance(ctx, dict):
            return
        if ctx.get("type") != self._pick_context_type:
            return
        rid = ctx.get("id")
        if not isinstance(rid, str) or not rid:
            return

        if not self._apply_pick_payload_to_model(rid, ev.payload):
            return

        self.update_tree_row(rid)

        # if current is same, allow subclass to sync form widgets
        if self.current_id == rid:
            self._sync_form_after_pick(rid, ev.payload)

        self.mark_dirty()
        if getattr(self._ctx.base.io, "auto_save", False):
            if self._save_to_disk():
                self.clear_dirty()

    # ----- hooks for subclasses -----
    def _apply_pick_payload_to_model(self, rid: str, payload: dict) -> bool:
        """
        Update underlying model with payload (x,y,r,g,b, optional monitor, etc).
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def _sync_form_after_pick(self, rid: str, payload: dict) -> None:
        """
        Optional: update UI variables after pick.
        """
        return