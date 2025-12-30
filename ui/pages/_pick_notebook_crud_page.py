# File: ui/pages/_pick_notebook_crud_page.py
from __future__ import annotations

import tkinter as tk

import ttkbootstrap as tb

from ui.pages._record_crud_page import RecordCrudPage
from ui.widgets.scrollable_frame import ScrollableFrame
from ui.app.notify import UiNotify


SAMPLE_DISPLAY_TO_VALUE = {"单像素": "single", "方形均值": "mean_square"}
SAMPLE_VALUE_TO_DISPLAY = {v: k for k, v in SAMPLE_DISPLAY_TO_VALUE.items()}


class PickNotebookCrudPage(RecordCrudPage):
    """
    基于 RecordCrudPage 的右侧 Notebook 布局基类：
    - 左侧仍为通用 CRUD 列表
    - 右侧使用 Notebook 分标签页（如“基本 / 像素 / 备注”）
    - 不再负责 Pick 流程（取色流程由各子类 + AppWindow + PickCoordinator 协作完成）
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        ctx,
        notify: UiNotify,
        page_title: str,
        record_noun: str,
        columns,
        tab_names: list[str],
    ) -> None:
        super().__init__(
            master,
            ctx=ctx,
            notify=notify,
            page_title=page_title,
            record_noun=record_noun,
            columns=columns,
        )

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