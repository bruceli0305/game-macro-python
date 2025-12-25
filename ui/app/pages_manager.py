from __future__ import annotations

import logging
import tkinter as tk
from typing import Dict

import ttkbootstrap as tb

from core.event_bus import EventBus
from core.profiles import ProfileContext
from core.app.services.app_services import AppServices

from ui.pages.base_settings import BaseSettingsPage
from ui.pages.skills import SkillsPage
from ui.pages.points import PointsPage

log = logging.getLogger(__name__)


class PagesManager:
    def __init__(self, *, master: tk.Misc, ctx: ProfileContext, bus: EventBus, services: AppServices) -> None:
        self._master = master
        self._ctx = ctx
        self._bus = bus
        self._services = services
        self.pages: Dict[str, tb.Frame] = {}

        self.pages["base"] = BaseSettingsPage(master, ctx=ctx, bus=bus, services=services)
        self.pages["skills"] = SkillsPage(master, ctx=ctx, bus=bus, services=services)
        self.pages["points"] = PointsPage(master, ctx=ctx, bus=bus, services=services)

        for p in self.pages.values():
            p.grid(row=0, column=0, sticky="nsew")

    def show(self, key: str) -> bool:
        page = self.pages.get(key)
        if page is None:
            return False
        page.tkraise()
        return True

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        for k, p in self.pages.items():
            if hasattr(p, "set_context"):
                try:
                    p.set_context(ctx)  # type: ignore[attr-defined]
                except Exception:
                    log.exception("PagesManager.set_context failed on page=%s", k)

    def flush_all(self) -> None:
        """
        Flush UI -> model before saves/switch.
        Priority: flush_to_model() then legacy _apply_form_to_current()
        """
        for k, p in self.pages.items():
            if hasattr(p, "flush_to_model"):
                try:
                    p.flush_to_model()  # type: ignore[attr-defined]
                    continue
                except Exception:
                    log.exception("PagesManager.flush_to_model failed on page=%s", k)

            if hasattr(p, "_apply_form_to_current"):
                try:
                    p._apply_form_to_current(auto_save=False)  # type: ignore[attr-defined]
                except Exception:
                    log.exception("PagesManager._apply_form_to_current flush failed on page=%s", k)