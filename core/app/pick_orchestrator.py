from __future__ import annotations

from typing import Optional

from core.event_bus import EventBus, Event
from core.event_types import EventType
from core.app.services.app_services import AppServices


class PickOrchestrator:
    """
    Application-level handler for pick results.

    Responsibilities:
    - listen to PICK_CONFIRMED
    - update domain model via AppServices (skills/points)
    - optionally auto-save via UoW
    - notify UI via RECORD_UPDATED
    - notify dirty state via DIRTY_STATE_CHANGED
    """

    def __init__(self, *, bus: EventBus, services: AppServices) -> None:
        self._bus = bus
        self._services = services

        self._bus.subscribe(EventType.PICK_CONFIRMED, self._on_pick_confirmed)

    def _on_pick_confirmed(self, ev: Event) -> None:
        payload = ev.payload
        ctx = payload.get("context")
        if not isinstance(ctx, dict):
            return

        typ = ctx.get("type")
        rid = ctx.get("id")
        if not isinstance(typ, str) or not isinstance(rid, str) or not rid:
            return

        # coordinates: prefer vx/vy (new), fallback to abs_x/abs_y
        vx_raw = payload.get("vx", payload.get("abs_x", 0))
        vy_raw = payload.get("vy", payload.get("abs_y", 0))
        try:
            vx = int(vx_raw)
            vy = int(vy_raw)
        except Exception:
            vx, vy = 0, 0

        # monitor used (pick_service already resolved cross-monitor)
        mon = payload.get("monitor", "")
        monitor = mon if isinstance(mon, str) else ""
        if not monitor:
            # fallback: requested monitor if present
            req = payload.get("monitor_requested", "")
            monitor = req if isinstance(req, str) else ""

        # rgb
        try:
            r = int(payload.get("r", 0))
            g = int(payload.get("g", 0))
            b = int(payload.get("b", 0))
        except Exception:
            r = g = b = 0

        applied = False
        part: Optional[str] = None

        if typ == "skill_pixel":
            applied = self._services.skills.apply_pick(rid, vx=vx, vy=vy, monitor=monitor, r=r, g=g, b=b)
            part = "skills"
        elif typ == "point":
            applied = self._services.points.apply_pick(rid, vx=vx, vy=vy, monitor=monitor, r=r, g=g, b=b)
            part = "points"
        else:
            return

        if not applied:
            return

        # dirty changed (applied)
        try:
            self._services.notify_dirty()
        except Exception:
            pass

        # autosave?
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

            # dirty may have changed again after commit
            try:
                self._services.notify_dirty()
            except Exception:
                pass

        # Notify UI to refresh list/form + dirty indicator decisions
        self._bus.post(
            EventType.RECORD_UPDATED,
            record_type=typ,  # "skill_pixel" | "point"
            id=rid,
            source="pick",
            saved=bool(saved),
        )

        # Optional user feedback
        hx = payload.get("hex", "")
        if isinstance(hx, str) and hx:
            if saved:
                self._bus.post(EventType.INFO, msg=f"取色已应用并保存: {hx}")
            else:
                self._bus.post(EventType.STATUS, msg=f"取色已应用(未保存): {hx}")