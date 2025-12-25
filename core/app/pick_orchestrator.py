from __future__ import annotations

from typing import Optional

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.events.utils import pick_confirmed_from_payload
from core.app.services.app_services import AppServices


class PickOrchestrator:
    """
    Application-level handler for pick results.
    Now consumes typed PickConfirmedPayload (still accepts dict for compatibility).
    """

    def __init__(self, *, bus: EventBus, services: AppServices) -> None:
        self._bus = bus
        self._services = services

        self._bus.subscribe(EventType.PICK_CONFIRMED, self._on_pick_confirmed)

    def _on_pick_confirmed(self, ev: Event) -> None:
        p = pick_confirmed_from_payload(ev.payload)
        if p is None:
            return

        typ = p.context.type
        rid = p.context.id

        applied = False
        part: Optional[str] = None

        if typ == "skill_pixel":
            applied = self._services.skills.apply_pick(
                rid, vx=p.vx, vy=p.vy, monitor=p.monitor, r=p.r, g=p.g, b=p.b
            )
            part = "skills"
        elif typ == "point":
            applied = self._services.points.apply_pick(
                rid, vx=p.vx, vy=p.vy, monitor=p.monitor, r=p.r, g=p.g, b=p.b
            )
            part = "points"
        else:
            return

        if not applied:
            return

        try:
            self._services.notify_dirty()
        except Exception:
            pass

        saved = False
        try:
            auto = bool(getattr(self._services.ctx.base.io, "auto_save", False))
        except Exception:
            auto = False

        if auto and part is not None:
            try:
                self._services.uow.commit(
                    parts={part},
                    backup=bool(self._services.ctx.base.io.backup_on_save),
                    touch_meta=False,
                )
                saved = True
            except Exception as e:
                self._bus.post(EventType.ERROR, msg=f"自动保存失败: {e}")
                saved = False

            try:
                self._services.notify_dirty()
            except Exception:
                pass

        # UI refresh
        self._bus.post(
            EventType.RECORD_UPDATED,
            record_type=typ,
            id=rid,
            source="pick",
            saved=bool(saved),
        )

        # feedback
        if p.hex:
            if saved:
                self._bus.post(EventType.INFO, msg=f"取色已应用并保存: {p.hex}")
            else:
                self._bus.post(EventType.STATUS, msg=f"取色已应用(未保存): {p.hex}")